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

    # formatos aceptados
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y",          #soporta 27-11-2025
        "%d/%m/%Y",
        "%Y/%m/%d",
    ]

    for fmt in formats:
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

    # === NUEVO estado dinámico ===
    base["is_active"] = (
        loan.issued_by_user_id is not None
        and loan.loaded_at is not None
        and loan.returned_at is None
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
    @role_required("admin", "manager","archivist")
    def get(self):
        """Lista de préstamos (filtrable por query, fechas y activos)."""

        from sqlalchemy import or_, and_, desc

        # paginación segura
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

        # búsqueda libre
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

        # filtros de fechas
        if loaded_after:
            q = q.filter(Loan.loaded_at >= loaded_after)
        if loaded_before:
            q = q.filter(Loan.loaded_at <= loaded_before)
        if returned_after:
            q = q.filter(Loan.returned_at >= returned_after)
        if returned_before:
            q = q.filter(Loan.returned_at <= returned_before)

        # ============================
        # ⚡ FILTRO active/inactive
        # ============================
        if active is not None:
            is_active = active.lower() in ("true", "1", "yes")

            if is_active:
                # préstamo activo → emitido, cargado, no devuelto
                q = q.filter(
                    Loan.issued_by_user_id.isnot(None),
                    Loan.loaded_at.isnot(None),
                    Loan.returned_at.is_(None),
                )
            else:
                # préstamo inactivo → no iniciado o devuelto
                q = q.filter(
                    or_(
                        # nunca iniciado
                        and_(
                            Loan.issued_by_user_id.is_(None),
                            Loan.loaded_at.is_(None),
                        ),
                        # devuelto
                        Loan.returned_at.isnot(None),
                    )
                )

        # orden por mas reciente
        q = q.order_by(desc(Loan.loaded_at), desc(Loan.id))

        # paginado estilo Funds
        paginated = q.paginate(page=page, per_page=per_page, error_out=False)
        items = paginated.items

        loans = [_serialize_loan(l) for l in items]

        return {
            "message": "Préstamos obtenidos correctamente.",
            "loans": loans,
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
    @role_required("admin", "manager","archivist")
    def get(self, loan_id: int):
        """Obtiene un préstamo."""
        loan = Loan.query.get(loan_id)
        if not loan or loan.deleted_at is not None:
            return {"message": "Préstamo no encontrado."}, 404
        return {"message": "Préstamo obtenido correctamente.", "loan": _serialize_loan(loan)}, 200

    @login_required
    @role_required("admin", "manager","archivist")
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
    @role_required("admin", "manager","archivist")
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

@api.route("/receive-by-record-file/<int:record_file_id>")
class LoanReceiveByRecordFile(Resource):
    @login_required
    @role_required("admin", "manager","archivist")
    def put(self, record_file_id: int):
        """
        Marca como devuelto el préstamo activo del expediente.
        Recibe: record_file_id
        Busca el préstamo activo más reciente.
        """

        # 1. Buscar expediente
        rf = RecordFile.query.get(record_file_id)
        if not rf or rf.deleted_at is not None:
            return {"message": "El expediente no existe o está eliminado."}, 404

        # 2. Verificar si está prestado
        if rf.availability_status != "on_loan":
            return {
                "message": "El expediente no está prestado actualmente.",
                "current_availability_status": rf.availability_status,
            }, 400

        # 3. Buscar el préstamo activo más reciente
        last_active_loan = (
            Loan.query
            .filter(
                Loan.record_file_id == record_file_id,
                Loan.deleted_at.is_(None),
                Loan.returned_at.is_(None),         # préstamo NO devuelto
                Loan.loaded_at.isnot(None)          # préstamo iniciado
            )
            .order_by(Loan.loaded_at.desc(), Loan.id.desc())
            .first()
        )

        if not last_active_loan:
            return {
                "message": "No existe un préstamo activo para este expediente."
            }, 404

        # 4. Marcar devolución
        last_active_loan.loaded_by_user_id = current_user.id
        last_active_loan.returned_at = db.func.now()
        rf.availability_status = "available"

        try:
            last_active_loan.updated_at = db.func.now()
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al guardar devolución.",
                "error": str(e),
            }, 500

        return {
            "message": "Préstamo del expediente marcado como devuelto.",
            "loan": _serialize_loan(last_active_loan),
        }, 200
