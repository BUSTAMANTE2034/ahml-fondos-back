"""Endpoints de gestión de expedientes documentales (JSON)."""

from datetime import datetime

from flask import request
from flask_login import login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy import or_, and_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.record_file import RecordFile
from app.models.fund import Fund
from app.models.section import Section
from app.models.series import Series
from app.models.location import Location
from app.models.deterioration import Deterioration
from app.models.typology import Typology
from app.models.record_file_typology import RecordFileTypology
from app.models.user import User  # <- para filtrar por nombre de usuario
from app.schemas.record_file import (
    RecordFileCreateSchema,
    RecordFileUpdateSchema,
    RecordFileResponseSchema,
)
from app.utils.security import role_required

api = Namespace("record-files", description="Operaciones de gestión de expedientes documentales")


def _parse_date(date_str: str):
    """Intenta parsear una fecha 'YYYY-MM-DD'. Devuelve None si falla."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _validate_active_entity(entity, entity_name: str = "Entidad"):
    """
    Valida que una entidad exista, no esté eliminada y, si tiene is_active, que esté activa.
    Devuelve un string con el error o None si está bien.
    """
    if not entity:
        return f"{entity_name} no encontrada."
    if getattr(entity, "deleted_at", None) is not None:
        return f"{entity_name} está eliminada y no puede usarse."
    if hasattr(entity, "is_active") and entity.is_active is False:
        return f"{entity_name} está inactiva y no puede usarse."
    return None


def _apply_ordering(query, order_by_param: str):
    """
    Aplica ordenamiento según el valor recibido.
    Valores permitidos:
        - created_at_asc / created_at_desc
        - updated_at_asc / updated_at_desc
        - file_date_asc / file_date_desc
        - deterioration_updated_at_asc / deterioration_updated_at_desc
    Por defecto: updated_at_desc
    """
    if not order_by_param:
        return query.order_by(RecordFile.updated_at.desc())

    mapping = {
        "created_at_asc": RecordFile.created_at.asc(),
        "created_at_desc": RecordFile.created_at.desc(),
        "updated_at_asc": RecordFile.updated_at.asc(),
        "updated_at_desc": RecordFile.updated_at.desc(),
        "file_date_asc": RecordFile.file_date.asc(),
        "file_date_desc": RecordFile.file_date.desc(),
        "deterioration_updated_at_asc": RecordFile.deterioration_status_updated_at.asc(),
        "deterioration_updated_at_desc": RecordFile.deterioration_status_updated_at.desc(),
    }

    sort_expr = mapping.get(order_by_param)
    if not sort_expr:
        # valor desconocido -> default
        return query.order_by(RecordFile.updated_at.desc())

    return query.order_by(sort_expr)


def _serialize_record_file(obj: RecordFile):
    """
    Serializa el expediente con todas las relaciones anidadas:
    - user
    - fund
    - section
    - series
    - location
    - deterioration_status
    - typologies (solo activas)
    """
    base = RecordFileResponseSchema().dump(obj)

    base["user"] = (
        {
            "id": obj.user.id,
            "first_name": obj.user.first_name,
            "last_name": obj.user.last_name,
            "email": obj.user.email,
        }
        if obj.user
        else None
    )

    base["fund"] = (
        {
            "id": obj.fund.id,
            "name": obj.fund.name,
            "acronym": obj.fund.acronym,
            "start_date": obj.fund.start_date.isoformat() if obj.fund.start_date else None,
            "end_date": obj.fund.end_date.isoformat() if obj.fund.end_date else None,
        }
        if obj.fund
        else None
    )

    base["section"] = (
        {
            "id": obj.section.id,
            "name": obj.section.name,
            "acronym": obj.section.acronym,
            "start_date": obj.section.start_date.isoformat() if obj.section.start_date else None,
            "end_date": obj.section.end_date.isoformat() if obj.section.end_date else None,
        }
        if obj.section
        else None
    )

    base["series"] = (
        {
            "id": obj.series.id,
            "name": obj.series.name,
            "acronym": obj.series.acronym,
            "start_date": obj.series.start_date.isoformat() if obj.series.start_date else None,
            "end_date": obj.series.end_date.isoformat() if obj.series.end_date else None,
        }
        if obj.series
        else None
    )

    base["location"] = (
        {
            "id": obj.location.id,
            "name": obj.location.name,
        }
        if obj.location
        else None
    )

    base["deterioration_status"] = (
        {
            "id": obj.deterioration_status.id,
            "name": obj.deterioration_status.name,
            "description": obj.deterioration_status.description,
            "updated_at": obj.deterioration_status_updated_at.isoformat()
            if obj.deterioration_status_updated_at
            else None,
        }
        if obj.deterioration_status
        else None
    )

    base["typologies"] = [
        {
            "id": rel.typology.id,
            "name": rel.typology.name,
            "description": rel.typology.description,
        }
        for rel in obj.record_file_typologies
        if rel.deleted_at is None
        and rel.typology
        and rel.typology.deleted_at is None
    ]

    return base


@api.route("")
class RecordFileList(Resource):
    @login_required
    @role_required("admin", "manager")
    def get(self):
        """
        Obtiene una lista paginada de expedientes no eliminados lógicamente.

        Descripción:
            Permite filtrar por códigos, texto libre, confidencialidad, disponibilidad,
            referencia archivística (por nombre y por id), ubicación, deterioro y tipologías.
            También permite filtrar por rangos de fecha de creación y de fecha documental,
            y ordenar los resultados por distintos campos.

        Parámetros de consulta:
            - page (int, opcional): Número de página. Por defecto 1.
            - per_page (int, opcional): Tamaño de página. Por defecto 20.

            Filtros textuales directos:
            - reference_code (str, opcional): Coincidencia parcial.
            - subject (str, opcional): Coincidencia parcial.
            - query (str, opcional): Búsqueda libre en reference_code, subject y comments.
            - box_number (str, opcional): Coincidencia parcial.
            - file_number (str, opcional): Coincidencia con el número de expediente.

            Filtros booleanos / de estado:
            - sensitive_data (bool|str, opcional): "true"/"false"/"1"/"0".
            - availability_status (str, opcional): "available" | "unavailable" | "under_review" | "on_loan".

            Filtros por relación usando **nombre**:
            - user_name (str, opcional): Busca por nombre, apellido o email del usuario.
            - fund_name (str, opcional): Coincidencia parcial con el nombre o acrónimo del fondo.
            - section_name (str, opcional): Coincidencia parcial con el nombre o acrónimo de la sección.
            - series_name (str, opcional): Coincidencia parcial con el nombre o acrónimo de la serie.
            - location_name (str, opcional): Coincidencia parcial con el nombre de la ubicación.
            - deterioration_name (str, opcional): Coincidencia parcial con el nombre del deterioro.
            - typology_name (str, opcional): Coincidencia parcial con el nombre de la tipología.

            (aún se aceptan IDs)
            - user_id (int, opcional)
            - fund_id (int, opcional)
            - section_id (int, opcional)
            - series_id (int, opcional)
            - location_id (int, opcional)
            - deterioration_status_id (int, opcional)
            - typology_id (int, opcional)

            Rangos de fecha de creación (sobre created_at):
            - created_after (date, opcional, YYYY-MM-DD)
            - created_before (date, opcional, YYYY-MM-DD)

            Rangos de fecha documental (sobre file_date):
            - file_date_after (date, opcional, YYYY-MM-DD)
            - file_date_before (date, opcional, YYYY-MM-DD)

            Ordenamiento:
            - order_by (str, opcional): Uno de
                "created_at_asc", "created_at_desc",
                "updated_at_asc", "updated_at_desc",
                "file_date_asc", "file_date_desc",
                "deterioration_updated_at_asc", "deterioration_updated_at_desc".
              Por defecto: "updated_at_desc".

        Respuestas:
            200: {
                "message": "Expedientes obtenidos correctamente.",
                "record_files": [...],
                "pagination": {...}
            }
        """
        # parámetros de paginación
        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 20))
        except ValueError:
            page = 1
            per_page = 20

        # parámetros textuales
        ref_param = request.args.get("reference_code", "").strip()
        subject_param = request.args.get("subject", "").strip()
        query_param = request.args.get("query", "").strip()
        box_number_param = request.args.get("box_number", "").strip()

        # estados / booleanos
        sensitive_param = request.args.get("sensitive_data")
        availability_param = request.args.get("availability_status")
        file_number_param = request.args.get("file_number", "").strip()

        # nombres de relaciones
        user_name_param = request.args.get("user_name", "").strip()
        fund_name_param = request.args.get("fund_name", "").strip()
        section_name_param = request.args.get("section_name", "").strip()
        series_name_param = request.args.get("series_name", "").strip()
        location_name_param = request.args.get("location_name", "").strip()
        deterioration_name_param = request.args.get("deterioration_name", "").strip()
        typology_name_param = request.args.get("typology_name", "").strip()

        # ids (por si acaso)
        user_id_param = request.args.get("user_id")
        fund_id_param = request.args.get("fund_id")
        section_id_param = request.args.get("section_id")
        series_id_param = request.args.get("series_id")
        location_id_param = request.args.get("location_id")
        det_status_param = request.args.get("deterioration_status_id")
        typology_id_param = request.args.get("typology_id")

        # rangos de fecha
        created_after_param = request.args.get("created_after")
        created_before_param = request.args.get("created_before")
        file_date_after_param = request.args.get("file_date_after")
        file_date_before_param = request.args.get("file_date_before")

        # orden
        order_by_param = request.args.get("order_by")

        query = RecordFile.query.filter(RecordFile.deleted_at.is_(None))

        # filtros directos
        if ref_param:
            query = query.filter(RecordFile.reference_code.ilike(f"%{ref_param}%"))

        if subject_param:
            query = query.filter(RecordFile.subject.ilike(f"%{subject_param}%"))

        if box_number_param:
            query = query.filter(RecordFile.box_number.ilike(f"%{box_number_param}%"))
        
        if file_number_param:
            query = query.filter(RecordFile.file_number.ilike(f"%{file_number_param}%"))
        if sensitive_param is not None:
            is_sensitive = sensitive_param.lower() in ("true", "1", "yes")
            query = query.filter(RecordFile.sensitive_data.is_(is_sensitive))

        if availability_param:
            query = query.filter(RecordFile.availability_status == availability_param)

        # búsqueda libre
        if query_param:
            like = f"%{query_param}%"
            query = query.filter(
                or_(
                    RecordFile.reference_code.ilike(like),
                    RecordFile.subject.ilike(like),
                    RecordFile.comments.ilike(like),
                )
            )

        # filtros por ID clásicos
        if user_id_param:
            try:
                uid = int(user_id_param)
                query = query.filter(RecordFile.user_id == uid)
            except ValueError:
                pass

        for field, param in [
            (RecordFile.fund_id, fund_id_param),
            (RecordFile.section_id, section_id_param),
            (RecordFile.series_id, series_id_param),
            (RecordFile.location_id, location_id_param),
        ]:
            if param:
                try:
                    pid = int(param)
                    query = query.filter(field == pid)
                except ValueError:
                    pass

        if det_status_param:
            try:
                det_id = int(det_status_param)
                query = query.filter(RecordFile.deterioration_status_id == det_id)
            except ValueError:
                pass

        # filtros por NOMBRE -> hacemos joins condicionales
        if user_name_param:
            like = f"%{user_name_param}%"
            query = query.join(User, User.id == RecordFile.user_id).filter(
                or_(
                    User.first_name.ilike(like),
                    User.last_name.ilike(like),
                    User.email.ilike(like),
                )
            )

        if fund_name_param:
            like = f"%{fund_name_param}%"
            query = query.join(Fund, Fund.id == RecordFile.fund_id).filter(
                or_(
                    Fund.name.ilike(like),
                    Fund.acronym.ilike(like),
                )
            )

        if section_name_param:
            like = f"%{section_name_param}%"
            query = query.join(Section, Section.id == RecordFile.section_id).filter(
                or_(
                    Section.name.ilike(like),
                    Section.acronym.ilike(like),
                )
            )

        if series_name_param:
            like = f"%{series_name_param}%"
            query = query.join(Series, Series.id == RecordFile.series_id).filter(
                or_(
                    Series.name.ilike(like),
                    Series.acronym.ilike(like),
                )
            )

        if location_name_param:
            like = f"%{location_name_param}%"
            query = query.join(Location, Location.id == RecordFile.location_id).filter(
                Location.name.ilike(like)
            )

        if deterioration_name_param:
            like = f"%{deterioration_name_param}%"
            query = query.join(Deterioration, Deterioration.id == RecordFile.deterioration_status_id).filter(
                Deterioration.name.ilike(like)
            )

        if typology_name_param:
            like = f"%{typology_name_param}%"
            # join a la tabla puente + typology, considerando solo relaciones activas
            query = query.join(
                RecordFileTypology,
                and_(
                    RecordFileTypology.record_file_id == RecordFile.id,
                    RecordFileTypology.deleted_at.is_(None),
                ),
            ).join(
                Typology,
                and_(
                    Typology.id == RecordFileTypology.typology_id,
                    Typology.deleted_at.is_(None),
                ),
            ).filter(Typology.name.ilike(like))

        # también permitir typology_id directo
        if typology_id_param:
            try:
                t_id = int(typology_id_param)
                query = query.join(
                    RecordFileTypology,
                    and_(
                        RecordFileTypology.record_file_id == RecordFile.id,
                        RecordFileTypology.deleted_at.is_(None),
                        RecordFileTypology.typology_id == t_id,
                    ),
                )
            except ValueError:
                pass

        # rangos de fecha de creación
        created_after = _parse_date(created_after_param)
        created_before = _parse_date(created_before_param)
        if created_after:
            query = query.filter(RecordFile.created_at >= datetime.combine(created_after, datetime.min.time()))
        if created_before:
            query = query.filter(RecordFile.created_at <= datetime.combine(created_before, datetime.max.time()))

        # rangos de fecha documental
        file_date_after = _parse_date(file_date_after_param)
        file_date_before = _parse_date(file_date_before_param)
        if file_date_after:
            query = query.filter(RecordFile.file_date >= file_date_after)
        if file_date_before:
            query = query.filter(RecordFile.file_date <= file_date_before)

        # ordenamiento
        query = _apply_ordering(query, order_by_param)

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        items = paginated.items

        return {
            "message": "Expedientes obtenidos correctamente.",
            "record_files": [_serialize_record_file(rf) for rf in items],
            "pagination": {
                "total": paginated.total,
                "pages": paginated.pages,
                "current_page": paginated.page,
                "per_page": paginated.per_page,
                "has_next": paginated.has_next,
                "has_prev": paginated.has_prev,
                "next_page": paginated.next_num if paginated.has_next else None,
                "prev_page": paginated.prev_num if paginated.has_prev else None,
            },
        }, 200


    @login_required
    @role_required("admin", "manager")
    def post(self):
        """
        Represents a documentary record file (expediente) in the AHML Fondos system.

        Descripción:
            Crea un nuevo expediente documental.
            Valida que fondo, sección, serie y ubicación existan, no estén eliminados
            y, si aplica, estén activos. Si se envía un deterioro, valida que exista
            y no esté eliminado. Si se envía una lista de tipologías, las vincula
            en la tabla puente (solo las que existan y no estén eliminadas).
            El código de referencia (reference_code) se genera automáticamente con
            la forma:
                FUND-SECCION-SERIE-C.{box_number}-Exp.{file_number}

        Cuerpo (JSON):
            - subject (str, requerido)
            - file_number (str, opcional)
            - sensitive_data (bool, opcional)
            - comments (str, opcional)
            - availability_status (str, opcional): "available"|"unavailable"|"under_review"|"on_loan"
            - fund_id (int, opcional)
            - section_id (int, opcional)
            - series_id (int, opcional)
            - location_id (int, opcional)
            - box_number (str, opcional)
            - page_count (int, opcional)
            - file_date (str, opcional, YYYY-MM-DD)
            - last_preservation_date (str, opcional, YYYY-MM-DD)
            - last_fund_date (str, opcional, YYYY-MM-DD)
            - deterioration_status_id (int, opcional)
            - typology_ids (array<int>, opcional)

        Respuestas:
            201: Expediente creado correctamente.
            400: Error de validación o referencia inexistente/inactiva.
        """
        schema = RecordFileCreateSchema()
        try:
            payload = request.get_json() or {}
            # asegurarnos de que NO intenten mandar reference_code
            payload.pop("reference_code", None)
            data = schema.load(payload)
            typology_ids = data.get("typology_ids")
            if typology_ids:
                # normalizar a lista de ints
                existing_ids = []
                missing_ids = []
                for tid in typology_ids:
                    try:
                        tid_int = int(tid)
                    except (TypeError, ValueError):
                        missing_ids.append(tid)
                        continue
                    
                    typ = Typology.query.get(tid_int)
                    if not typ or typ.deleted_at is not None:
                        missing_ids.append(tid_int)
                    else:
                        existing_ids.append(tid_int)

                if missing_ids:
                    return {
                        "message": "Algunas tipologías no existen o están eliminadas.",
                        "missing_typology_ids": missing_ids,
                    }, 400
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        # validar referencias
        fund = None
        section = None
        serie = None
        location = None

        fund_id = data.get("fund_id")
        if fund_id:
            fund = Fund.query.get(fund_id)
            err = _validate_active_entity(fund, "Fondo")
            if err:
                return {"message": err}, 400

        section_id = data.get("section_id")
        if section_id:
            section = Section.query.get(section_id)
            err = _validate_active_entity(section, "Sección")
            if err:
                return {"message": err}, 400

        series_id = data.get("series_id")
        if series_id:
            serie = Series.query.get(series_id)
            err = _validate_active_entity(serie, "Serie")
            if err:
                return {"message": err}, 400

        location_id = data.get("location_id")
        if location_id:
            location = Location.query.get(location_id)
            err = _validate_active_entity(location, "Ubicación")
            if err:
                return {"message": err}, 400

        det_id = data.get("deterioration_status_id")
        if det_id:
            det = Deterioration.query.get(det_id)
            if not det or det.deleted_at is not None:
                return {
                    "message": "El deterioro especificado no existe o está eliminado."
                }, 400
        if _exists_record_file_with_number_global(data.get("file_number")):
            return {
        "message": "Ya existe un expediente con ese número.",
        "file_number": data.get("file_number"),
    }, 400

        # construir reference_code
        ref_code = _build_reference_code(
            fund=fund,
            section=section,
            serie=serie,
            box_number=data.get("box_number"),
            file_number=data.get("file_number"),
        )

        rf = RecordFile(
            reference_code=ref_code,
            subject=data["subject"],
            file_number=data.get("file_number"),
            sensitive_data=data.get("sensitive_data", False),
            comments=data.get("comments"),
            availability_status=data.get("availability_status", "available"),
            fund_id=fund_id,
            section_id=section_id,
            series_id=series_id,
            location_id=location_id,
            box_number=data.get("box_number"),
            page_count=data.get("page_count"),
            file_date=data.get("file_date"),
            last_preservation_date=data.get("last_preservation_date"),
            last_fund_date=data.get("last_fund_date"),
            deterioration_status_id=det_id,
            deterioration_status_updated_at=db.func.now() if det_id else None,
            user_id=current_user.id if current_user.is_authenticated else None,
        )

        db.session.add(rf)
        db.session.flush()  # ya tenemos rf.id

        typology_ids = data.get("typology_ids")
        if typology_ids:
            _sync_record_file_typologies(rf, typology_ids)

        db.session.commit()

        return {
            "message": "Expediente creado correctamente.",
            "record_file": _serialize_record_file(rf),
        }, 201


@api.route("/<int:record_file_id>")
class RecordFileDetail(Resource):
    @login_required
    @role_required("admin", "manager")
    def get(self, record_file_id: int):
        """
        Represents a documentary record file (expediente) in the AHML Fondos system.

        Descripción:
            Obtiene un expediente específico por su identificador, siempre que no
            esté eliminado lógicamente. Incluye los datos del usuario, las referencias
            archivísticas (fondo, sección, serie), la ubicación, el deterioro y las
            tipologías activas vinculadas.

        Parámetros de ruta:
            - record_file_id (int): Identificador del expediente.

        Respuestas:
            200: Expediente obtenido correctamente.
            404: Expediente no encontrado o eliminado.
        """
        rf = RecordFile.query.get(record_file_id)
        if not rf or rf.deleted_at is not None:
            return {"message": "Expediente no encontrado."}, 404

        return {
            "message": "Expediente obtenido correctamente.",
            "record_file": _serialize_record_file(rf),
        }, 200

    @login_required
    @role_required("admin", "manager")
    def put(self, record_file_id: int):
        """
        Represents a documentary record file (expediente) in the AHML Fondos system.

        Descripción:
            Actualiza parcialmente un expediente documental existente. Valida todas las
            referencias que se quieran cambiar (fondo, sección, serie, ubicación, deterioro),
            con las mismas reglas que en la creación:
                - deben existir
                - no deben estar eliminadas
                - fondo/sección/serie deben estar activas
            Si se envía la lista de tipologías, se sincroniza la tabla puente.
            Si se cambia algún dato que forma el código (fondo, sección, serie,
            box_number, file_number) se reconstruye el reference_code.

        Parámetros de ruta:
            - record_file_id (int): Identificador del expediente a actualizar.

        Cuerpo (JSON):
            - subject, file_number, sensitive_data, ...
            - typology_ids (array<int>, opcional)

        Respuestas:
            200: Expediente actualizado correctamente.
            400: Error de validación o referencia inválida/inactiva.
            404: Expediente no encontrado.
        """
        schema = RecordFileUpdateSchema()
        try:
            payload = request.get_json() or {}
            payload["id"] = record_file_id
            # no permitir que el cliente actualice el reference_code explícitamente
            payload.pop("reference_code", None)
            data = schema.load(payload)
            typology_ids = data.get("typology_ids")
            if typology_ids:
                # normalizar a lista de ints
                existing_ids = []
                missing_ids = []
                for tid in typology_ids:
                    try:
                        tid_int = int(tid)
                    except (TypeError, ValueError):
                        missing_ids.append(tid)
                        continue
                    
                    typ = Typology.query.get(tid_int)
                    if not typ or typ.deleted_at is not None:
                        missing_ids.append(tid_int)
                    else:
                        existing_ids.append(tid_int)

                if missing_ids:
                    return {
                        "message": "Algunas tipologías no existen o están eliminadas.",
                        "missing_typology_ids": missing_ids,
                    }, 400
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        rf = RecordFile.query.get(record_file_id)
        if not rf or rf.deleted_at is not None:
            return {"message": "Expediente no encontrado."}, 404

        # vamos a necesitar estos objetos para reconstruir el código al final
        fund = rf.fund
        section = rf.section
        serie = rf.series

        rebuild_code = False

        # fondo
        if "fund_id" in data:
            fid = data["fund_id"]
            if fid is not None:
                fund = Fund.query.get(fid)
                err = _validate_active_entity(fund, "Fondo")
                if err:
                    return {"message": err}, 400
            else:
                fund = None
            rf.fund_id = fid
            rebuild_code = True

        # sección
        if "section_id" in data:
            sid = data["section_id"]
            if sid is not None:
                section = Section.query.get(sid)
                err = _validate_active_entity(section, "Sección")
                if err:
                    return {"message": err}, 400
            else:
                section = None
            rf.section_id = sid
            rebuild_code = True

        # serie
        if "series_id" in data:
            seid = data["series_id"]
            if seid is not None:
                serie = Series.query.get(seid)
                err = _validate_active_entity(serie, "Serie")
                if err:
                    return {"message": err}, 400
            else:
                serie = None
            rf.series_id = seid
            rebuild_code = True

        # ubicación
        if "location_id" in data:
            lid = data["location_id"]
            if lid is not None:
                loc = Location.query.get(lid)
                err = _validate_active_entity(loc, "Ubicación")
                if err:
                    return {"message": err}, 400
            rf.location_id = lid

        # deterioro
        if "deterioration_status_id" in data:
            did = data["deterioration_status_id"]

            # guardar el valor anterior para comparar
            old_deterioration_id = rf.deterioration_status_id

            if did is not None:
                det = Deterioration.query.get(did)
                if not det or det.deleted_at is not None:
                    return {
                        "message": "El deterioro especificado no existe o está eliminado."
                    }, 400

            # asignar el nuevo (puede ser None)
            rf.deterioration_status_id = did

            # solo si cambió el valor, actualizamos la fecha
            if did != old_deterioration_id:
                rf.deterioration_status_updated_at = db.func.now()

        # campos simples
        for field in [
            "subject",
            "sensitive_data",
            "comments",
            "availability_status",
            "page_count",
            "file_date",
            "last_preservation_date",
            "last_fund_date",
        ]:
            if field in data:
                setattr(rf, field, data[field])

        # estos dos impactan en el reference_code
        if "box_number" in data:
            rf.box_number = data["box_number"]
            rebuild_code = True
        if "file_number" in data:
            rf.file_number = data["file_number"]
            rebuild_code = True
        if rf.file_number:
            exists_q = (
                RecordFile.query
                .filter(
                    RecordFile.deleted_at.is_(None),
                    RecordFile.file_number == rf.file_number,
                    RecordFile.id != rf.id,        # excluir el mismo
                )
                .first()
            )
            if exists_q:
                return {
                    "message": "Ya existe otro expediente con ese número.",
                    "file_number": rf.file_number,
                }, 400
        # tipologías
        if "typology_ids" in data:
            _sync_record_file_typologies(rf, data["typology_ids"])

        # si cambió algo que afecta el código, lo regeneramos
        if rebuild_code:
            new_code = _build_reference_code(
                fund=fund,
                section=section,
                serie=serie,
                box_number=rf.box_number,
                file_number=rf.file_number,
            )
            rf.reference_code = new_code

        # quién modificó
        rf.user_id = current_user.id if current_user.is_authenticated else rf.user_id

        try:
            rf.updated_at = db.func.now()
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al guardar en base de datos.",
                "error": str(e),
            }, 500

        return {
            "message": "Expediente actualizado correctamente.",
            "record_file": _serialize_record_file(rf),
        }, 200

    @login_required
    @role_required("admin", "manager")
    def delete(self, record_file_id: int):
        """
        Represents a documentary record file (expediente) in the AHML Fondos system.

        Descripción:
            Realiza un borrado lógico del expediente, marcándolo como eliminado
            y registrando el usuario que hizo la eliminación.

        Parámetros de ruta:
            - record_file_id (int): Identificador del expediente a eliminar.

        Respuestas:
            200: Expediente eliminado correctamente.
            404: Expediente no encontrado.
        """
        rf = RecordFile.query.get(record_file_id)
        if not rf or rf.deleted_at is not None:
            return {"message": "Expediente no encontrado."}, 404

        rf.deleted_at = db.func.now()
        rf.user_id = current_user.id if current_user.is_authenticated else rf.user_id

        db.session.commit()

        return {"message": "Expediente eliminado correctamente."}, 200
