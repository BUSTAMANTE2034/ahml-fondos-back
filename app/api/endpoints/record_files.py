from collections import defaultdict
from datetime import datetime

from flask import request, make_response
from flask_login import login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional

from app.extensions import db
from app.models.record_file import RecordFile
from app.models.fund import Fund
from app.models.section import Section
from app.models.series import Series
from app.models.location import Location
from app.models.deterioration import Deterioration
from app.models.typology import Typology
from app.schemas.record_file import (
    RecordFileCreateSchema,
    RecordFileUpdateSchema,
)
from app.utils.security import role_required
from app.models.box import Box

from app.services.record_file_services import (
    build_cover_page,
    _build_record_file_query_from_request,
    _parse_date,
    _validate_active_entity,
    _apply_ordering,
    _serialize_record_file,
    _build_record_files_pdf,
    _build_reference_code,
    _exists_record_file_with_number_global,
    _sync_record_file_typologies, _build_record_file_query_for_export, timestamp_es, _build_record_files_excel, _generate_next_file_number
)


api = Namespace(
    "record-files",
    description="Operaciones de gestión de expedientes documentales",
)

def can_modify_record_file(rf: RecordFile, user) -> bool:
    if not user.is_authenticated:
        return False

    if user.role in ("admin", "manager"):
        return True

    return rf.user_id == user.id


@api.route("")
class RecordFileList(Resource):
    @login_required
    @role_required("admin", "manager", "archivist", "visitor")
    def get(self):
        """
        Obtiene una lista paginada de expedientes documentales no eliminados lógicamente.

        Descripción:
            Permite aplicar filtros por búsqueda libre, filtros por nombre de fondo/sección/serie,
            ubicación, deterioro y tipologías, así como filtros de confidencialidad, disponibilidad
            y rangos de fecha documental (`file_date`). También permite ordenar los resultados por
            distintos campos de fecha.

        Parámetros de consulta (query string):

        Paginación:
            - page (int, opcional):
                Número de página. Por defecto 1.
            - per_page (int, opcional):
                Tamaño de página. Por defecto 20.

        Búsqueda global:
            - query (str, opcional):
                Término de búsqueda libre. Coincidencia parcial sobre:
                    * reference_code
                    * file_number
                    *  box (derivado de la caja física, Box.box_number)

        Mini-queries por campo:
            - reference_code (str, opcional):
                Coincidencia parcial sobre `RecordFile.reference_code`.
            - file_number (str, opcional):
                Coincidencia parcial sobre `RecordFile.file_number`.
            - box_number (derivado de la caja) (str, opcional):
                Filtro por caja física (`Box.id`)
            - fund_name (str, opcional):
                Coincidencia parcial sobre `Fund.name` o `Fund.acronym`.
            - section_name (str, opcional):
                Coincidencia parcial sobre `Section.name` o `Section.acronym`.
            - series_name (str, opcional):
                Coincidencia parcial sobre `Series.name` o `Series.acronym`.
            - location_name (str, opcional):
                Coincidencia parcial sobre `Location.name`.
            - deterioration_name (str, opcional):
                Coincidencia parcial sobre `Deterioration.name`.
            - typology_name (str, opcional):
                Coincidencia parcial sobre `Typology.name` a través de la relación
                de tipologías del expediente.

        Filtros de confidencialidad:
            - sensitive (str, opcional):
                Indica el tipo de confidencialidad. Valores esperados:
                    * "all" (por defecto): no se aplica filtro.
                    * "delicate": solo expedientes con `sensitive_data == True`.
                    * "not delicate": solo expedientes con `sensitive_data == False`.

        Filtros de disponibilidad:
            - availability_status (str, opcional):
                Estado de disponibilidad. Valores esperados:
                    * "all" (por defecto): no se aplica filtro.
                    * "available"
                    * "unavailable"
                    * "under_review"
                    * "on_loan"

        Filtros por fecha documental:
            - file_date_after (str, opcional):
                Fecha en formato "YYYY-MM-DD". Incluye expedientes con
                `file_date >= file_date_after`.
            - file_date_before (str, opcional):
                Fecha en formato "YYYY-MM-DD". Incluye expedientes con
                `file_date <= file_date_before`.
                Si se envían ambos parámetros, se consideran los expedientes cuyo
                `file_date` se encuentra dentro del intervalo [after, before].

        Ordenamiento:
            - order_by (str, opcional):
                Campo de ordenamiento. Valores soportados:
                    * "created_at_asc" / "created_at_desc"
                    * "updated_at_asc" / "updated_at_desc"
                    * "file_date_asc" / "file_date_desc"
                    * "deterioration_status_updated_at_asc"
                      "deterioration_status_updated_at_desc"
                El orden siempre se aplica primero por disponibilidad (estado) y
                luego por el campo indicado.
        """
        # --- Paginación ---
        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 20))
        except ValueError:
            page = 1
            per_page = 20

        # --- Construcción del query con TODOS los filtros soportados ---
        query = _build_record_file_query_from_request(request)
        paginated = query.paginate(
            page=page, per_page=per_page, error_out=False)
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
    @role_required("admin", "manager", "archivist")
    def post(self):
        """
        Represents a documentary record file (expediente) in the AHML Fondos system.

        Descripción:
            Crea un nuevo expediente documental.
            Valida que fondo, sección, serie y ubicación existan, no estén eliminados
            y, si aplica, estén activos. Si se envía un deterioro, valida que exista
            y no esté eliminado. Si se envía una lista de tipologías, las vincula
            en la tabla puente (solo las que existan y no estén eliminadas).
            El código de referencia (reference_code) se genera automáticamente.
        """
        user_id = current_user.id
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

        # if _exists_record_file_with_number_global(data.get("file_number")):
        #     return {
        #         "message": "Ya existe un expediente con ese número.",
        #         "file_number": data.get("file_number"),
        #     }, 400

        # construir reference_code (función que ya tienes en otro lado)

        file_number = _generate_next_file_number(
            fund_id=fund_id,
            section_id=section_id,
            series_id=series_id,
            box_id=data.get("box_id"),
        )
        VALID_AVAILABILITY = {"available", "unavailable", "under_review", "on_loan"}

        status = data.get("availability_status", "available")
        if status not in VALID_AVAILABILITY:
            return {
                "message": "Estado de disponibilidad inválido.",
                "availability_status": status,
            }, 400

        box = None
        box_id = data.get("box_id")
        if box_id:
            box = Box.query.get(box_id)
            if not box or box.deleted_at is not None:
                return {"message": "La caja no existe o está eliminada."}, 400
            if not box.is_active:
                return {"message": "La caja está inactiva."}, 400

        ref_code = _build_reference_code(
            fund=fund,
            section=section,
            serie=serie,
            box=box,
            file_number=file_number,
        )

        rf = RecordFile(
            reference_code=ref_code,
            previous_reference_code=data.get("previous_reference_code"),
            subject=data["subject"],
            file_number=file_number,
            sensitive_data=data.get("sensitive_data", False),
            comments=data.get("comments"),
            availability_status=data.get("availability_status", "available"),
            fund_id=fund_id,
            section_id=section_id,
            series_id=series_id,
            location_id=location_id,
            box_id=data.get("box_id"),
            page_count=data.get("page_count"),
            document_sizes=data.get("document_sizes"),
            file_date=data.get("file_date"),
            last_preservation_date=data.get("last_preservation_date"),
            last_fund_date=data.get("last_fund_date"),
            deterioration_status_id=det_id,
            deterioration_status_updated_at=db.func.now() if det_id else None,
            user_id=user_id ,
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
    @role_required("admin", "manager", "archivist", "visitor")
    def get(self, record_file_id: int):
        """
        Obtiene un expediente específico por su identificador.
        """
        rf = RecordFile.query.get(record_file_id)
        if not rf or rf.deleted_at is not None:
            return {"message": "Expediente no encontrado."}, 404

        return {
            "message": "Expediente obtenido correctamente.",
            "record_file": _serialize_record_file(rf),
        }, 200

    @login_required
    @role_required("admin", "manager", "archivist")
    def put(self, record_file_id: int):
        """
        Actualiza un expediente documental existente.
        Si cambia el grupo (fondo, sección, serie o caja),
        se recalcula automáticamente el file_number.
        """

        # -----------------------------
        # VALIDACIÓN INICIAL
        # -----------------------------
        user_id = current_user.id
        schema = RecordFileUpdateSchema()
        try:
            payload = request.get_json() or {}
            payload["id"] = record_file_id
            payload.pop("reference_code", None)
            payload.pop("file_number", None)  # ⛔ NO se acepta

            data = schema.load(payload, partial=True)

            # validar tipologías
            if "typology_ids" in data:
                missing_ids = []
                for tid in data["typology_ids"]:
                    typ = Typology.query.get(tid)
                    if not typ or typ.deleted_at is not None:
                        missing_ids.append(tid)

                if missing_ids:
                    return {
                        "message": "Algunas tipologías no existen o están eliminadas.",
                        "missing_typology_ids": missing_ids,
                    }, 400

        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        # -----------------------------
        # OBTENER EXPEDIENTE
        # -----------------------------
        rf = RecordFile.query.get(record_file_id)
        if not rf or rf.deleted_at is not None:
            return {"message": "Expediente no encontrado."}, 404
        if not can_modify_record_file(rf, current_user):
            return {
        "message": "No tienes permisos para modificar este expediente."
    }, 403
        # valores actuales
        fund = rf.fund
        section = rf.section
        serie = rf.series

        rebuild_code = False
        group_changed = False

        # -----------------------------
        # FONDO
        # -----------------------------
        if "fund_id" in data and data["fund_id"] != rf.fund_id:
            fund = Fund.query.get(data["fund_id"]) if data["fund_id"] else None
            err = _validate_active_entity(fund, "Fondo")
            if err:
                return {"message": err}, 400

            rf.fund_id = data["fund_id"]
            rebuild_code = True
            group_changed = True

        # -----------------------------
        # SECCIÓN
        # -----------------------------
        if "section_id" in data and data["section_id"] != rf.section_id:
            section = Section.query.get(
                data["section_id"]) if data["section_id"] else None
            err = _validate_active_entity(section, "Sección")
            if err:
                return {"message": err}, 400

            rf.section_id = data["section_id"]
            rebuild_code = True
            group_changed = True

        # -----------------------------
        # SERIE
        # -----------------------------
        if "series_id" in data and data["series_id"] != rf.series_id:
            serie = Series.query.get(
                data["series_id"]) if data["series_id"] else None
            err = _validate_active_entity(serie, "Serie")
            if err:
                return {"message": err}, 400

            rf.series_id = data["series_id"]
            rebuild_code = True
            group_changed = True

        # -----------------------------
        # CAJA
        # -----------------------------
        if "box_id" in data and data["box_id"] != rf.box_id:
            box = Box.query.get(data["box_id"]) if data["box_id"] else None
            if box:
                if box.deleted_at is not None:
                    return {"message": "La caja no existe o está eliminada."}, 400
                if not box.is_active:
                    return {"message": "La caja está inactiva."}, 400

            rf.box_id = data["box_id"]
            rebuild_code = True
            group_changed = True

        # -----------------------------
        # UBICACIÓN
        # -----------------------------
        if "location_id" in data and data["location_id"] != rf.location_id:
            loc = Location.query.get(
                data["location_id"]) if data["location_id"] else None
            err = _validate_active_entity(loc, "Ubicación")
            if err:
                return {"message": err}, 400

            rf.location_id = data["location_id"]

        # -----------------------------
        # DETERIORO
        # -----------------------------
        if "deterioration_status_id" in data and data["deterioration_status_id"] != rf.deterioration_status_id:
            det = Deterioration.query.get(
                data["deterioration_status_id"]) if data["deterioration_status_id"] else None
            if det and det.deleted_at is not None:
                return {
                    "message": "El deterioro especificado no existe o está eliminado."
                }, 400

            rf.deterioration_status_id = data["deterioration_status_id"]
            rf.deterioration_status_updated_at = db.func.now()

        # -----------------------------
        # CAMPOS SIMPLES
        # -----------------------------
        for field in [
            "previous_reference_code",
            "subject",
            "sensitive_data",
            "comments",
            "availability_status",
            "page_count",
            "file_date",
            "last_preservation_date",
            "last_fund_date",
            "document_sizes",
        ]:
            if field in data:
                setattr(rf, field, data[field])

        # -----------------------------
        # RECALCULAR FILE_NUMBER SI CAMBIÓ EL GRUPO
        # -----------------------------
        if group_changed:
            rf.file_number = _generate_next_file_number(
                fund_id=rf.fund_id,
                section_id=rf.section_id,
                series_id=rf.series_id,
                box_id=rf.box_id,
            )

        # -----------------------------
        # TIPOLÓGICAS
        # -----------------------------
        if "typology_ids" in data:
            _sync_record_file_typologies(rf, data["typology_ids"])

        # -----------------------------
        # REGENERAR CÓDIGO
        # -----------------------------
        if rebuild_code:
            rf.reference_code = _build_reference_code(
                fund=fund,
                section=section,
                serie=serie,
                box=rf.box,
                file_number=rf.file_number,
            )

        # -----------------------------
        # AUDITORÍA
        # -----------------------------
        rf.updated_by_id = user_id
        rf.updated_at = db.func.now()

        # -----------------------------
        # GUARDAR
        # -----------------------------
        try:
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
    @role_required("admin", "manager", "archivist")
    def delete(self, record_file_id: int):
        """
        Realiza un borrado lógico del expediente.
    """
        user_id = current_user.id
        rf = RecordFile.query.get(record_file_id)
        if not rf or rf.deleted_at is not None:
            return {"message": "Expediente no encontrado."}, 404
        if not can_modify_record_file(rf, current_user):
            return {
        "message": "No tienes permisos para eliminar este expediente."
    }, 403
        rf.deleted_at = db.func.now()
        rf.deleted_by_id = user_id

        db.session.commit()

        return {"message": "Expediente eliminado correctamente."}, 200


@api.route("/export-pdf")
class RecordFileExportPDF(Resource):
    @login_required
    @role_required("admin", "manager", "archivist", "visitor")
    def get(self):
        # reutilizamos TODOS los filtros del get normal
        query = _build_record_file_query_from_request(request)

        # por seguridad ponemos un tope
        max_rows = 1000
        record_files = query.limit(max_rows).all()

        pdf_buffer = _build_record_files_pdf(record_files)

        resp = make_response(pdf_buffer.read())
        resp.headers.set("Content-Type", "application/pdf")
        resp.headers.set(
            "Content-Disposition",
            "attachment",
            filename="reporte_expedientes.pdf",
        )
        return resp


@api.route("/print-cover-page")
class RecordFilePrintCoverPage(Resource):
    @login_required
    @role_required("admin", "manager", "archivist", "visitor")
    def get(self):
        """
        Genera la carátula (cover page) en PDF para un expediente.

        Uso:
            GET /record-files/print-cover-page?record_file_id=<id>

        Respuestas:
            200: PDF descargable.
            400: Falta el parámetro record_file_id.
            404: Expediente no encontrado.
        """
        record_file_id = request.args.get("record_file_id", type=int)
        if not record_file_id:
            return {"message": "El parámetro 'record_file_id' es requerido."}, 400

        rf = RecordFile.query.get(record_file_id)
        if not rf or rf.deleted_at is not None:
            return {"message": "Expediente no encontrado."}, 404

        pdf_buffer = build_cover_page(rf)

        resp = make_response(pdf_buffer.read())
        resp.headers.set("Content-Type", "application/pdf")
        resp.headers.set(
            "Content-Disposition",
            "attachment",
            filename=f"caratula_expediente_{rf.id}.pdf",
        )
        return resp


@api.route("/export-excel")
class RecordFileExportExcel(Resource):
    @login_required
    @role_required("admin", "manager", "archivist")
    def get(self):

        # ✔ construir query usando filtros del request
        query = _build_record_file_query_from_request(request)

        # ✔ cantidad solicitada
        try:
            per_page = int(request.args.get("per_page", 50))
        except:
            per_page = 50

        per_page = min(per_page, 50000)

        # ✔ obtener expedientes filtrados
        record_files = query.limit(per_page).all()

        # ✔ construir Excel final
        excel_buffer = _build_record_files_excel(record_files)

        fecha_str = timestamp_es()

        resp = make_response(excel_buffer.read())
        resp.headers.set(
            "Content-Type",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp.headers.set(
            "Content-Disposition",
            f'attachment; filename="reporte_expedientes({fecha_str}).xlsx"'
        )
        return resp


@api.route("/reorder-by-file-date")
class RecordFileReorderByDate(Resource):

    @login_required
    @role_required("admin", "manager", "archivist")
    def put(self):
        
        """
        Reordena los file_number de los expedientes
        por fondo-sección-serie-caja usando file_date
        (del más antiguo al más reciente).

        Filtros opcionales por query params:
        ?fund_id=&section_id=&series_id=&box_number=
        """
        user_id = current_user.id
        # -----------------------------
        # LEER QUERY PARAMS
        # -----------------------------
        fund_id = request.args.get("fund_id", type=int)
        section_id = request.args.get("section_id", type=int)
        series_id = request.args.get("series_id", type=int)
        box_id = request.args.get("box_id", type=int)

        # -----------------------------
        # CONSTRUIR QUERY BASE
        # -----------------------------
        query = RecordFile.query.filter(
            RecordFile.deleted_at.is_(None)
        )

        # filtros dinámicos (solo si vienen)
        if fund_id:
            query = query.filter(RecordFile.fund_id == fund_id)

        if section_id:
            query = query.filter(RecordFile.section_id == section_id)

        if series_id is not None:
            query = query.filter(RecordFile.series_id == series_id)

        if box_id is not None:
            query = query.filter(RecordFile.box_id == box_id)

        # -----------------------------
        # OBTENER EXPEDIENTES
        # -----------------------------
        record_files = query.order_by(
            RecordFile.fund_id,
            RecordFile.section_id,
            RecordFile.series_id,
            RecordFile.box_id,
            RecordFile.file_date.is_(None),  # NULLs al final
            RecordFile.file_date,
            RecordFile.created_at,
        ).all()

        if not record_files:
            return {"message": "No hay expedientes para reordenar."}, 200

        # -----------------------------
        # AGRUPAR POR (fondo, sección, serie, caja)
        # -----------------------------
        grouped = defaultdict(list)

        for rf in record_files:
            key = (
                rf.fund_id,
                rf.section_id,
                rf.series_id,
                rf.box_id,
            )
            grouped[key].append(rf)

        # -----------------------------
        # REORDENAR CADA GRUPO
        # -----------------------------
        updated_count = 0

        for (_, _, _, _), files in grouped.items():

            files.sort(
                key=lambda r: (
                    r.file_date is None,   # None al final
                    r.file_date,
                    r.created_at,
                )
            )

            for idx, rf in enumerate(files, start=1):
                new_file_number = str(idx)

                if rf.file_number != new_file_number:
                    rf.file_number = new_file_number

                    rf.reference_code = _build_reference_code(
                        fund=rf.fund,
                        section=rf.section,
                        serie=rf.series,
                        box=rf.box,
                        file_number=new_file_number,
                    )

                    rf.updated_at = db.func.now()
                    # rf.updated_by_id = user_id
                    updated_count += 1

        # -----------------------------
        # GUARDAR CAMBIOS
        # -----------------------------
        try:
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al reordenar expedientes.",
                "error": str(e),
            }, 500

        return {
            "message": "Expedientes reordenados correctamente.",
            "updated_records": updated_count,
        }, 200
