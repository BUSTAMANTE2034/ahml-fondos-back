"""
Endpoints de gestión de Revisiones / Diagnósticos de Expedientes.

Una revisión representa un acto técnico de evaluación sobre un expediente,
con una sola observación general y múltiples conceptos/detalles asociados.
"""
from datetime import datetime
from flask import request
from flask_login import login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.record_diagnosis import RecordDiagnosis
from app.models.record_file import RecordFile
from app.models.diagnosis_catalog import DiagnosisCatalog

from app.schemas.record_diagnosis import (
    RecordDiagnosisCreateSchema,
    RecordDiagnosisResponseSchema,
)
from app.utils.security import role_required
from sqlalchemy import desc, or_

api = Namespace(
    "record_diagnosis",
    description="Operaciones de gestión de revisiones de expedientes",
)
def _parse_date(date_str: str):
    """Acepta formatos YYYY-MM-DD y DD-MM-YYYY."""
    if not date_str:
        return None

    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            pass

    return None


@api.route("")
class RecordDiagnosisList(Resource):

    @login_required
    @role_required("admin", "manager", "archivist")
    def get(self):
        """
        Obtiene lista paginada de revisiones no eliminadas lógicamente,
        con filtros por expediente, usuario y rango de fechas.
        """
        record_file_id_param = request.args.get("record_file_id")
        user_id_param = request.args.get("user_id")
        start_date_param = request.args.get("start_date")
        end_date_param = request.args.get("end_date")
        query_param = request.args.get("query")
        diagnosis_detail_param = request.args.get("diagnosis_detail")

        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 20))
        except ValueError:
            page = 1
            per_page = 20

        query = RecordDiagnosis.query.filter(
            RecordDiagnosis.deleted_at.is_(None)
        )
        if query_param:
            like = f"%{query_param.strip()}%"

            query = query.join(
                RecordFile, RecordDiagnosis.record_file
            ).outerjoin(
                RecordDiagnosis.user
            ).filter(
                or_(
                    RecordFile.previous_reference_code.ilike(like),
                    RecordFile.reference_code.ilike(like),
                    
                    RecordDiagnosis.observations.ilike(like),
                    db.func.concat(
                        current_user.first_name, ' ', current_user.last_name
                    ).ilike(like),
                )
            )

        # filtro por expediente
        if record_file_id_param:
            try:
                rid = int(record_file_id_param)
                query = query.filter(RecordDiagnosis.record_file_id == rid)
            except ValueError:
                pass
        if diagnosis_detail_param:
            like = f"%{diagnosis_detail_param.strip()}%"

            query = query.join(
                RecordDiagnosis.diagnosis_catalog
            ).filter(
                or_(
                    DiagnosisCatalog.detail.ilike(like),
                    DiagnosisCatalog.description.ilike(like),
                    # DiagnosisCatalog.description.ilike(like),
                )
            )

        # filtro por usuario revisor
        if user_id_param:
            try:
                uid = int(user_id_param)
                query = query.filter(RecordDiagnosis.user_id == uid)
            except ValueError:
                pass
        start_date_filter= _parse_date(start_date_param)
        end_date_filter = _parse_date(end_date_param)
        # filtros por fecha
        if start_date_param:
            query = query.filter(
                RecordDiagnosis.revision_date >= start_date_filter
            )
        if end_date_param:
            query = query.filter(
                RecordDiagnosis.revision_date <= end_date_filter
            )

        from sqlalchemy import desc
        query = query.order_by(desc(RecordDiagnosis.revision_date))

        paginated = query.paginate(
            page=page, per_page=per_page, error_out=False
        )

        schema = RecordDiagnosisResponseSchema(many=True)
        data = schema.dump(paginated.items)

        return {
            "message": "Revisiones obtenidas correctamente.",
            "record_diagnoses": data,
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
        Crea una nueva revisión de expediente con múltiples
        conceptos/detalles asociados.
        """
        user_id=current_user.id
        schema = RecordDiagnosisCreateSchema()
        try:
            payload = request.get_json() or {}
            data = schema.load(payload)
        except ValidationError as err:
            return {
                "message": "Error de validación.",
                "errors": err.messages,
            }, 400

        record_file = RecordFile.query.get(data["record_file_id"])
        if not record_file or record_file.deleted_at is not None:
            return {"message": "Expediente no encontrado."}, 404

        diagnosis_items = DiagnosisCatalog.query.filter(
            DiagnosisCatalog.id.in_(data["diagnosis_catalog_ids"]),
            DiagnosisCatalog.deleted_at.is_(None),
            DiagnosisCatalog.is_active.is_(True),
        ).all()

        if not diagnosis_items:
            return {
                "message": "No se encontraron conceptos de diagnóstico válidos."
            }, 400

        diagnosis = RecordDiagnosis(
            record_file_id=record_file.id,
            user_id=user_id,
            observations=data.get("observations"),
        )

        diagnosis.diagnosis_catalog.extend(diagnosis_items)

        db.session.add(diagnosis)
        db.session.commit()

        schema_resp = RecordDiagnosisResponseSchema()
        return {
            "message": "Revisión creada correctamente.",
            "record_diagnosis": schema_resp.dump(diagnosis),
        }, 201


@api.route("/<int:diagnosis_id>")
class RecordDiagnosisDetail(Resource):

    @login_required
    @role_required("admin", "manager", "archivist")
    def get(self, diagnosis_id: int):
        """
        Obtiene una revisión por ID.
        """
        diagnosis = RecordDiagnosis.query.get(diagnosis_id)
        if not diagnosis or diagnosis.deleted_at is not None:
            return {"message": "Revisión no encontrada."}, 404

        schema = RecordDiagnosisResponseSchema()
        return {
            "message": "Revisión obtenida correctamente.",
            "record_diagnosis": schema.dump(diagnosis),
        }, 200

    @login_required
    @role_required("admin", "manager", "archivist")
    def put(self, diagnosis_id: int):
        """
        Actualiza una revisión existente.
        Permite modificar observaciones y los conceptos asociados.
        """
        schema = RecordDiagnosisCreateSchema()
        try:
            payload = request.get_json() or {}
            payload["record_file_id"] = payload.get(
                "record_file_id"
            ) or 0
            data = schema.load(payload, partial=True)
        except ValidationError as err:
            return {
                "message": "Error de validación.",
                "errors": err.messages,
            }, 400

        diagnosis = RecordDiagnosis.query.get(diagnosis_id)
        if not diagnosis or diagnosis.deleted_at is not None:
            return {"message": "Revisión no encontrada."}, 404

        if "observations" in data:
            diagnosis.observations = data["observations"]

        if "diagnosis_catalog_ids" in data:
            diagnosis_items = DiagnosisCatalog.query.filter(
                DiagnosisCatalog.id.in_(data["diagnosis_catalog_ids"]),
                DiagnosisCatalog.deleted_at.is_(None),
                DiagnosisCatalog.is_active.is_(True),
            ).all()

            diagnosis.diagnosis_catalog.clear()
            diagnosis.diagnosis_catalog.extend(diagnosis_items)

        try:
            diagnosis.updated_at = db.func.now()
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al guardar en base de datos.",
                "error": str(e),
            }, 500

        schema_resp = RecordDiagnosisResponseSchema()
        return {
            "message": "Revisión actualizada correctamente.",
            "record_diagnosis": schema_resp.dump(diagnosis),
        }, 200

    @login_required
    @role_required("admin", "manager", "archivist")
    def delete(self, diagnosis_id: int):
        """
        Borrado lógico de una revisión.
        """
        diagnosis = RecordDiagnosis.query.get(diagnosis_id)
        if not diagnosis or diagnosis.deleted_at is not None:
            return {"message": "Revisión no encontrada."}, 404

        diagnosis.deleted_at = db.func.now()
        db.session.commit()

        return {
            "message": "Revisión eliminada correctamente."
        }, 200
