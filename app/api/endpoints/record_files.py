"""Endpoints de gestión de expedientes documentales (JSON)."""

from datetime import datetime

from flask import request
from flask_login import login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy import or_, and_
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional
from typing import Optional
from app.extensions import db
from app.models.record_file import RecordFile
from app.models.fund import Fund
from app.models.section import Section
from app.models.series import Series
from app.models.location import Location
from app.models.deterioration import Deterioration
from app.models.typology import Typology
from app.models.record_file_typology import RecordFileTypology
from app.schemas.record_file import (
    RecordFileCreateSchema,
    RecordFileUpdateSchema,
    RecordFileResponseSchema,
)
from app.utils.security import role_required

api = Namespace("record-files", description="Operaciones de gestión de expedientes documentales")


# =====================================================================================
# Helpers
# =====================================================================================
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


def _build_reference_code(
    fund: Optional[Fund],
    section: Optional[Section],
    serie: Optional[Series],
    box_number: Optional[str],
    file_number: Optional[str],
) -> str:
    """
    Genera el reference_code con la regla:
        FUNDACR-SECTIONACR-SERIESACR-C.{box}-Exp.{file}

    - Si no hay fondo/sección/serie se omiten.
    - Si no hay box_number no se pone el segmento C.x
    - Si no hay file_number se pone Exp.s/n
    """
    parts = []

    if fund and fund.acronym:
        parts.append(fund.acronym)
    elif fund:
        parts.append(fund.name)

    if section and section.acronym:
        parts.append(section.acronym)
    elif section:
        parts.append(section.name)

    if serie and serie.acronym:
        parts.append(serie.acronym)
    elif serie:
        parts.append(serie.name)

    # base: FUND-SECT-SERIE
    base_code = "-".join(parts) if parts else "EXP"

    # caja
    if box_number:
        base_code = f"{base_code}-C.{box_number}"

    # expediente
    if file_number:
        base_code = f"{base_code}-Exp.{file_number}"
    else:
        base_code = f"{base_code}-Exp.s/n"

    return base_code


def _sync_record_file_typologies(record_file, incoming_ids):
    """
    Sincroniza las tipologías ligadas a un expediente.

    Reglas:
    - Si no llega lista -> no hace nada.
    - Las que están activas y ya no vienen -> se marcan deleted_at.
    - Las que vienen y ya existen pero estaban borradas lógicamente -> se reactivan (deleted_at = NULL).
    - Las que vienen y no existen -> se insertan.
    - Solo se consideran tipologías que existen y no están borradas.
    """
    if incoming_ids is None:
        return

    # normalizar: aceptar 1 solo id o lista
    if isinstance(incoming_ids, int):
        incoming_ids = [incoming_ids]

    if not isinstance(incoming_ids, (list, tuple, set)):
        return

    # limpiar a ints
    clean_ids = []
    for v in incoming_ids:
        try:
            clean_ids.append(int(v))
        except (TypeError, ValueError):
            continue

    incoming_set = set(clean_ids)

    # traer TODAS las relaciones actuales (activas o borradas) de este expediente
    current_by_typ = {
        rel.typology_id: rel
        for rel in record_file.record_file_typologies
    }

    # 1. desactivar las que están activas y YA no vienen
    for rel in record_file.record_file_typologies:
        if rel.deleted_at is None and rel.typology_id not in incoming_set:
            rel.deleted_at = db.func.now()

    # 2. procesar las que vienen
    for typ_id in incoming_set:
        existing_rel = current_by_typ.get(typ_id)

        if existing_rel:
            # ya hay una fila para este record_file + typology
            if existing_rel.deleted_at is not None:
                # estaba “borrada” -> reactivarla
                existing_rel.deleted_at = None
                existing_rel.updated_at = db.func.now()
            # si ya estaba activa, no hacemos nada
            continue

        # no existe relación -> validar que la tipología exista
        typ = Typology.query.get(typ_id)
        if not typ or typ.deleted_at is not None:
            # tipología inválida -> la saltamos
            continue

        db.session.add(
            RecordFileTypology(
                record_file_id=record_file.id,
                typology_id=typ_id,
            )
        )

def _exists_record_file_with_number_global(
    file_number: str,
    exclude_id: Optional[int] = None,
) -> bool:
    q = RecordFile.query.filter(
        RecordFile.deleted_at.is_(None),
        RecordFile.file_number == file_number,
    )
    if exclude_id is not None:
        q = q.filter(RecordFile.id != exclude_id)
    return q.first() is not None


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

    # user
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

    # fund
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

    # section
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

    # series
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

    # location
    base["location"] = (
        {
            "id": obj.location.id,
            "name": obj.location.name,
        }
        if obj.location
        else None
    )

    # deterioration
    base["deterioration_status"] = (
        {
            "id": obj.deterioration_status.id,
            "name": obj.deterioration_status.name,
            "description": obj.deterioration_status.description,
        }
        if obj.deterioration_status
        else None
    )

    # typologies
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



# =====================================================================================
# Rutas
# =====================================================================================
@api.route("")
class RecordFileList(Resource):
    @login_required
    @role_required("admin", "manager")
    def get(self):
        """
        Represents a documentary record file (expediente) in the AHML Fondos system.

        Descripción:
            Obtiene una lista paginada de expedientes no eliminados lógicamente.
            Permite aplicar filtros por:
            - código de referencia (reference_code)
            - asunto (subject)
            - búsqueda libre (query)
            - confidencialidad (sensitive_data)
            - estado de disponibilidad (availability_status)
            - usuario creador/modificador (user_id)
            - fondo, sección, serie, ubicación (por ID)
            - número de caja (box_number)
            - rango de fecha documental (file_date_from / file_date_to)
            - rango de fecha de creación (created_from / created_to)
            - deterioro (deterioration_status_id)
            - tipología (typology_id)

        Parámetros de consulta:
            - page (int, opcional): Número de página. Por defecto 1.
            - per_page (int, opcional): Tamaño de página. Por defecto 20.
            - reference_code (str, opcional): Filtra por coincidencia parcial.
            - subject (str, opcional): Filtra por coincidencia parcial en el asunto.
            - query (str, opcional): Busca en reference_code, subject y comments.
            - sensitive_data (bool|str, opcional): "true"/"false"/"1"/"0".
            - availability_status (str, opcional): "available" | "unavailable" | "under_review" | "on_loan".
            - user_id (int, opcional): ID del usuario que creó/modificó.
            - fund_id (int, opcional): ID del fondo.
            - section_id (int, opcional): ID de la sección.
            - series_id (int, opcional): ID de la serie.
            - location_id (int, opcional): ID de la ubicación.
            - box_number (str, opcional): Coincidencia parcial.
            - file_date_from (date, opcional, YYYY-MM-DD): Fecha documental inicial.
            - file_date_to (date, opcional, YYYY-MM-DD): Fecha documental final.
            - created_from (date, opcional, YYYY-MM-DD): Fecha de creación inicial.
            - created_to (date, opcional, YYYY-MM-DD): Fecha de creación final.
            - deterioration_status_id (int, opcional): ID del deterioro asociado.
            - typology_id (int, opcional): ID de la tipología asociada.

        Respuestas:
            200: {...}
        """
        ref_param = request.args.get("reference_code", "").strip()
        subject_param = request.args.get("subject", "").strip()
        query_param = request.args.get("query", "").strip()
        sensitive_param = request.args.get("sensitive_data")
        availability_param = request.args.get("availability_status")
        user_id_param = request.args.get("user_id")
        fund_id_param = request.args.get("fund_id")
        section_id_param = request.args.get("section_id")
        series_id_param = request.args.get("series_id")
        location_id_param = request.args.get("location_id")
        box_number_param = request.args.get("box_number", "").strip()
        file_date_from_param = request.args.get("file_date_from")
        file_date_to_param = request.args.get("file_date_to")
        created_from_param = request.args.get("created_from")
        created_to_param = request.args.get("created_to")
        det_status_param = request.args.get("deterioration_status_id")
        typology_id_param = request.args.get("typology_id")

        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 20))
        except ValueError:
            page = 1
            per_page = 20

        query = RecordFile.query.filter(RecordFile.deleted_at.is_(None))

        if ref_param:
            query = query.filter(RecordFile.reference_code.ilike(f"%{ref_param}%"))

        if subject_param:
            query = query.filter(RecordFile.subject.ilike(f"%{subject_param}%"))

        if sensitive_param is not None:
            is_sensitive = sensitive_param.lower() in ("true", "1", "yes")
            query = query.filter(RecordFile.sensitive_data.is_(is_sensitive))

        if availability_param:
            query = query.filter(RecordFile.availability_status == availability_param)

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

        if box_number_param:
            query = query.filter(RecordFile.box_number.ilike(f"%{box_number_param}%"))

        ffrom = _parse_date(file_date_from_param)
        fto = _parse_date(file_date_to_param)
        if ffrom:
            query = query.filter(RecordFile.file_date >= ffrom)
        if fto:
            query = query.filter(RecordFile.file_date <= fto)

        cfrom = _parse_date(created_from_param)
        cto = _parse_date(created_to_param)
        if cfrom:
            query = query.filter(RecordFile.created_at >= datetime.combine(cfrom, datetime.min.time()))
        if cto:
            query = query.filter(RecordFile.created_at <= datetime.combine(cto, datetime.max.time()))

        if det_status_param:
            try:
                det_id = int(det_status_param)
                query = query.filter(RecordFile.deterioration_status_id == det_id)
            except ValueError:
                pass

        if query_param:
            like = f"%{query_param}%"
            query = query.filter(
                or_(
                    RecordFile.reference_code.ilike(like),
                    RecordFile.subject.ilike(like),
                    RecordFile.comments.ilike(like),
                )
            )

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

        query = query.order_by(RecordFile.updated_at.desc())

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
            if did is not None:
                det = Deterioration.query.get(did)
                if not det or det.deleted_at is not None:
                    return {
                        "message": "El deterioro especificado no existe o está eliminado."
                    }, 400
            rf.deterioration_status_id = did
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
