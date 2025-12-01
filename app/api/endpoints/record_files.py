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
    _sync_record_file_typologies,_build_record_file_query_for_export,timestamp_es,_build_record_files_excel
)


api = Namespace(
    "record-files",
    description="Operaciones de gestión de expedientes documentales",
)


@api.route("")
class RecordFileList(Resource):
    @login_required
    @role_required("admin", "manager","archivist","visitor")
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
                    * box_number

        Mini-queries por campo:
            - reference_code (str, opcional):
                Coincidencia parcial sobre `RecordFile.reference_code`.
            - file_number (str, opcional):
                Coincidencia parcial sobre `RecordFile.file_number`.
            - box_number (str, opcional):
                Coincidencia parcial sobre `RecordFile.box_number`.
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
    @role_required("admin", "manager","archivist")
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
        ref_code = _build_reference_code(
            fund=fund,
            section=section,
            serie=serie,
            box_number=data.get("box_number"),
            file_number=data.get("file_number"),
        )

        rf = RecordFile(
            reference_code=ref_code,
            previous_reference_code=data.get("previous_reference_code"),
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
            document_sizes=data.get("document_sizes"),
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
    @role_required("admin", "manager","archivist","visitor")
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
    @role_required("admin", "manager","archivist")
    def put(self, record_file_id: int):
        """
        Actualiza un expediente documental existente.
        """

        # -----------------------------
        # VALIDACIÓN INICIAL DEL PAYLOAD
        # -----------------------------
        schema = RecordFileUpdateSchema()
        try:
            payload = request.get_json() or {}
            payload["id"] = record_file_id
            payload.pop("reference_code", None)  # evitar manipulación
            data = schema.load(payload, partial=True)

            typology_ids = data.get("typology_ids")
            if typology_ids:
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

        # -----------------------------
        # OBTENER EXPEDIENTE
        # -----------------------------
        rf = RecordFile.query.get(record_file_id)
        if not rf or rf.deleted_at is not None:
            return {"message": "Expediente no encontrado."}, 404

        # Guardamos valores actuales para posible rebuild
        fund = rf.fund
        section = rf.section
        serie = rf.series

        rebuild_code = False

        # -----------------------------
        # FONDO
        # -----------------------------
        if "fund_id" in data:
            fid = data["fund_id"]
            current_fid = rf.fund_id

            # Solo validamos si REALMENTE cambia el id
            if fid != current_fid:
                if fid is not None:
                    fund = Fund.query.get(fid)
                    err = _validate_active_entity(fund, "Fondo")
                    if err:
                        return {"message": err}, 400
                else:
                    fund = None

                rf.fund_id = fid
                rebuild_code = True
            else:
                # mismo fondo, no validamos ni tocamos rebuild_code
                fund = rf.fund

        # -----------------------------
        # SECCIÓN
        # -----------------------------
        if "section_id" in data:
            sid = data["section_id"]
            current_sid = rf.section_id

            if sid != current_sid:
                if sid is not None:
                    section = Section.query.get(sid)
                    err = _validate_active_entity(section, "Sección")
                    if err:
                        return {"message": err}, 400
                else:
                    section = None

                rf.section_id = sid
                rebuild_code = True
            else:
                section = rf.section
        # -----------------------------
        # SERIE
        # -----------------------------
        if "series_id" in data:
            seid = data["series_id"]
            current_seid = rf.series_id

            if seid != current_seid:
                if seid is not None:
                    serie = Series.query.get(seid)
                    err = _validate_active_entity(serie, "Serie")
                    if err:
                        return {"message": err}, 400
                else:
                    serie = None

                rf.series_id = seid
                rebuild_code = True
            else:
                serie = rf.series

        # -----------------------------
        # UBICACIÓN
        # -----------------------------
        if "location_id" in data:
            lid = data["location_id"]
            current_lid = rf.location_id

            if lid != current_lid:
                if lid is not None:
                    loc = Location.query.get(lid)
                    err = _validate_active_entity(loc, "Ubicación")
                    if err:
                        return {"message": err}, 400

                rf.location_id = lid
            # si es el mismo id, no hacemos nada

        # -----------------------------
        # DETERIORO
        # -----------------------------
        if "deterioration_status_id" in data:
            did = data["deterioration_status_id"]
            old_did = rf.deterioration_status_id

            if did != old_did:
                if did is not None:
                    det = Deterioration.query.get(did)
                    if not det or det.deleted_at is not None:
                        return {
                            "message": "El deterioro especificado no existe o está eliminado."
                        }, 400

                rf.deterioration_status_id = did
                rf.deterioration_status_updated_at = db.func.now()
            # si es el mismo id, no validamos ni tocamos la fecha

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
        # VALIDAR FILE_NUMBER (sin asignar)
        # -----------------------------
        new_box_number = rf.box_number
        new_file_number = rf.file_number

        if "box_number" in data:
            new_box_number = data["box_number"]
            rebuild_code = True

        if "file_number" in payload:
            new_file_number = data["file_number"]
            rebuild_code = True

        # Validación correcta: permitir el mismo file_number en este expediente
        if "file_number" in payload:
            new_file_number = data["file_number"]

            # solo validar si realmente lo cambiaron
            # if new_file_number != rf.file_number:
            #     exists_q = (
            #         RecordFile.query
            #         .filter(
            #             RecordFile.deleted_at.is_(None),
            #             RecordFile.file_number == new_file_number,
            #             RecordFile.id != rf.id,
            #         )
            #         .first()
            #     )
            #     if exists_q:
            #         return {
            #             "message": "Ya existe otro expediente con ese número.",
            #             "file_number": new_file_number,
            #         }, 400

            rf.file_number = new_file_number
            rebuild_code = True

        # SOLO después de validar, asignamos:
        rf.box_number = new_box_number
        # -----------------------------
        # TIPOLÓGICAS
        # -----------------------------
        if "typology_ids" in data:
            _sync_record_file_typologies(rf, data["typology_ids"])

        # -----------------------------
        # REGENERAR CÓDIGO SI CAMBIÓ ALGO
        # -----------------------------
        if rebuild_code:
            new_code = _build_reference_code(
                fund=fund,
                section=section,
                serie=serie,
                box_number=rf.box_number,
                file_number=rf.file_number,
            )
            rf.reference_code = new_code

        # -----------------------------
        # QUIÉN MODIFICÓ
        # -----------------------------
        rf.user_id = current_user.id if current_user.is_authenticated else rf.user_id

        # -----------------------------
        # GUARDAR
        # -----------------------------
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
    @role_required("admin", "manager","archivist")
    def delete(self, record_file_id: int):
        """
        Realiza un borrado lógico del expediente.
    """
        rf = RecordFile.query.get(record_file_id)
        if not rf or rf.deleted_at is not None:
            return {"message": "Expediente no encontrado."}, 404

        rf.deleted_at = db.func.now()
        rf.user_id = current_user.id if current_user.is_authenticated else rf.user_id

        db.session.commit()

        return {"message": "Expediente eliminado correctamente."}, 200


@api.route("/export-pdf")
class RecordFileExportPDF(Resource):
    @login_required
    @role_required("admin", "manager","archivist","visitor")
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
    @role_required("admin", "manager","archivist","visitor")
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
    @role_required("admin", "manager","archivist")
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
   