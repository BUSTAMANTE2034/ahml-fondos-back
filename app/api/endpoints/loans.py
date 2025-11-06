"""Endpoints de gestión de préstamos de expedientes (JSON)."""

from datetime import datetime

from flask import request
from flask_login import login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.record_file import RecordFile
from app.models.loan import Loan
from app.schemas.loan import (
    LoanCreateSchema,
    LoanUpdateSchema,
    LoanResponseSchema,
)
from app.utils.security import role_required

api = Namespace("loans", description="Operaciones de préstamos de expedientes")

BLOCKING_RECORD_STATUSES = ["on_loan", "under_review", "unavailable"]


# =========================
# Helpers
# =========================
def _parse_datetime(dt_str: str):
    if not dt_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return None


def _serialize_loan(loan: Loan):
    base = LoanResponseSchema().dump(loan)
    base["record_file"] = (
        {
            "id": loan.record_file.id,
            "reference_code": loan.record_file.reference_code,
            "availability_status": loan.record_file.availability_status,
            "file_number": loan.record_file.file_number,
        }
        if loan.record_file
        else None
    )

    base["issued_by_user"] = (
        {
            "id": loan.issued_by_user.id,
            "first_name": loan.issued_by_user.first_name,
            "last_name": loan.issued_by_user.last_name,
            "email": loan.issued_by_user.email,
        }
        if loan.issued_by_user
        else None
    )

    base["loaded_by_user"] = (
        {
            "id": loan.loaded_by_user.id,
            "first_name": loan.loaded_by_user.first_name,
            "last_name": loan.loaded_by_user.last_name,
            "email": loan.loaded_by_user.email,
        }
        if loan.loaded_by_user
        else None
    )
    return base


def _mark_record_on_loan(record_file: RecordFile):
    record_file.availability_status = "on_loan"


def _mark_record_available(record_file: RecordFile):
    record_file.availability_status = "available"


# =========================
# Rutas
# =========================
@api.route("")
class LoanList(Resource):
    @login_required
    @role_required("admin", "manager")
    def get(self):
        """Lista de préstamos (filtrable por query, fechas y activos)."""
        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 20))
        except ValueError:
            page, per_page = 1, 20

        query_text = request.args.get("query", "").strip()
        loaded_after = _parse_datetime(request.args.get("loaded_after"))
        loaded_before = _parse_datetime(request.args.get("loaded_before"))
        returned_after = _parse_datetime(request.args.get("returned_after"))
        returned_before = _parse_datetime(request.args.get("returned_before"))
        active = request.args.get("active")

        q = Loan.query.filter(Loan.deleted_at.is_(None))

        if query_text:
            like = f"%{query_text}%"
            q = (
                q.join(RecordFile, RecordFile.id == Loan.record_file_id)
                .filter(
                    or_(
                        RecordFile.file_number.ilike(like),
                        RecordFile.reference_code.ilike(like),
                    )
                )
            )

        if loaded_after:
            q = q.filter(Loan.loaded_at >= loaded_after)
        if loaded_before:
            q = q.filter(Loan.loaded_at <= loaded_before)
        if returned_after:
            q = q.filter(Loan.returned_at >= returned_after)
        if returned_before:
            q = q.filter(Loan.returned_at <= returned_before)

        if active and active.lower() in ("true", "1", "yes"):
            q = q.filter(or_(Loan.returned_at.is_(None), Loan.loaded_by_user_id.is_(None)))

        q = q.order_by(Loan.id.desc())
        paginated = q.paginate(page=page, per_page=per_page, error_out=False)

        return {
            "message": "Préstamos obtenidos correctamente.",
            "loans": [_serialize_loan(l) for l in paginated.items],
            "pagination": {
                "total": paginated.total,
                "pages": paginated.pages,
                "current_page": paginated.page,
                "per_page": paginated.per_page,
            },
        }, 200

    @login_required
    @role_required("admin", "manager")
    def post(self):
        """
        Crea un préstamo.
        Solo si el expediente está en estado 'available'.
        """
        schema = LoanCreateSchema()
        try:
            payload = request.get_json() or {}
            payload.pop("issued_by_user_id", None)
            payload.pop("loaded_by_user_id", None)
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        record_file_id = data["record_file_id"]
        description = data.get("description")

        rf = RecordFile.query.get(record_file_id)
        if not rf or rf.deleted_at is not None:
            return {"message": "El expediente no existe o está eliminado."}, 400

        # si NO está available, explicar por qué
        # si NO está available, explicar por qué
        if rf.availability_status != "available":
            # ver si hay un préstamo activo (para el caso on_loan)
            last_loan = (
                Loan.query
                .filter(
                    Loan.record_file_id == record_file_id,
                    Loan.deleted_at.is_(None),
                    Loan.returned_at.is_(None),
                )
                .order_by(Loan.loaded_at.desc(), Loan.id.desc())
                .first()
            )

            if rf.availability_status == "on_loan":
                if last_loan and last_loan.loaded_at:
                    return {
                        "message": "El expediente no está disponible porque está prestado.",
                        "loaned_at": last_loan.loaded_at.isoformat(),
                        "current_availability_status": rf.availability_status,
                        "loan_id": last_loan.id,
                    }, 400
                return {
                    "message": "El expediente no está disponible porque está prestado.",
                    "current_availability_status": rf.availability_status,
                }, 400

            if rf.availability_status == "under_review":
                return {
                    "message": "El expediente no está disponible porque está en revisión.",
                    "current_availability_status": rf.availability_status,
                    # si la tienes, mándala
                    "review_started_at": (
                        rf.last_preservation_date.isoformat()
                        if getattr(rf, "last_preservation_date", None)
                        else None
                    ),
                }, 400

            if rf.availability_status == "unavailable":
                return {
                    "message": "El expediente no está disponible.",
                    "current_availability_status": rf.availability_status,
                }, 400

            # fallback
            return {
                "message": f"El expediente no está disponible para préstamo (estado actual: {rf.availability_status})."
            }, 400

        # aquí sí está available → creamos el préstamo
        now = db.func.now()
        loan = Loan(
            record_file_id=record_file_id,
            issued_by_user_id=current_user.id if current_user.is_authenticated else None,
            loaded_by_user_id=None,
            description=description,
            loaded_at=now,
        )

        _mark_record_on_loan(rf)

        db.session.add(loan)
        try:
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": "Error al guardar en base de datos.", "error": str(e)}, 500

        return {
            "message": "Préstamo creado correctamente.",
            "loan": _serialize_loan(loan),
        }, 201



@api.route("/<int:loan_id>")
class LoanDetail(Resource):
    @login_required
    @role_required("admin", "manager")
    def get(self, loan_id: int):
        """Obtiene un préstamo."""
        loan = Loan.query.get(loan_id)
        if not loan or loan.deleted_at is not None:
            return {"message": "Préstamo no encontrado."}, 404
        return {"message": "Préstamo obtenido correctamente.", "loan": _serialize_loan(loan)}, 200

    @login_required
    @role_required("admin", "manager")
    def put(self, loan_id: int):
        """Actualiza solo la descripción del préstamo."""
        schema = LoanUpdateSchema()
        try:
            payload = request.get_json() or {}
            payload["id"] = loan_id
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        loan = Loan.query.get(loan_id)
        if not loan or loan.deleted_at is not None:
            return {"message": "Préstamo no encontrado."}, 404

        if "description" in data:
            loan.description = data["description"]

        try:
            loan.updated_at = db.func.now()
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": "Error al guardar en base de datos.", "error": str(e)}, 500

        return {"message": "Préstamo actualizado correctamente.", "loan": _serialize_loan(loan)}, 200


@api.route("/<int:loan_id>/receive")
class LoanReceive(Resource):
    @login_required
    @role_required("admin", "manager")
    def put(self, loan_id: int):
        """
        Endpoint de recepción del préstamo.
        Cierra el préstamo llenando:
        - loaded_by_user_id = current_user.id
        - returned_at = db.func.now()
        - expediente → available
        """
        loan = Loan.query.get(loan_id)
        if not loan or loan.deleted_at is not None:
            return {"message": "Préstamo no encontrado."}, 404

        rf = loan.record_file
        if not rf or rf.deleted_at is not None:
            return {"message": "El expediente asociado no existe o está eliminado."}, 400

        if loan.returned_at is not None:
            return {"message": "El préstamo ya fue marcado como devuelto."}, 400

        loan.loaded_by_user_id = current_user.id
        loan.returned_at = db.func.now()
        _mark_record_available(rf)

        try:
            loan.updated_at = db.func.now()
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": "Error al guardar recepción.", "error": str(e)}, 500

        return {"message": "Préstamo recibido y expediente devuelto.", "loan": _serialize_loan(loan)}, 200
