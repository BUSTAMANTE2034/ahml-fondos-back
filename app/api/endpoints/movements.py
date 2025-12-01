"""Endpoints de historial de movimientos de expedientes (JSON)."""

from datetime import datetime, date

from flask import request
from flask_login import login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.record_file import RecordFile
from app.models.movement import MovementHistory
from app.schemas.movement import (
    MovementHistoryCreateSchema,
    MovementHistoryUpdateSchema,
    MovementHistoryResponseSchema,
)
from typing import Optional

from app.utils.security import role_required

api = Namespace("movement-history", description="Operaciones de historial de movimientos de expedientes")

# AHORA USAMOS LOS ESTATUS DEL RECORD FILE
ALLOWED_STATUSES = ["available", "under_review", "unavailable"]


# ===========================
# HELPERS
# ===========================
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


def _serialize_movement(mov: MovementHistory, record_file: Optional[RecordFile] = None):
    base = MovementHistoryResponseSchema().dump(mov)
    rf = record_file or mov.record_file

    # Convertir fechas del expediente si existen
    if rf:
        base["record_file"] = {
            "id": rf.id,
            "reference_code": rf.reference_code,
            "availability_status": rf.availability_status,
            "last_preservation_date": (
                rf.last_preservation_date.isoformat()
                if isinstance(rf.last_preservation_date, (datetime, date))
                else rf.last_preservation_date
            ),
            "last_fund_date": (
                rf.last_fund_date.isoformat()
                if isinstance(rf.last_fund_date, (datetime, date))
                else rf.last_fund_date
            ),
        }

    # Datos del usuario que movió
    if mov.moved_by_user:
        base["moved_by_user"] = {
            "id": mov.moved_by_user.id,
            "first_name": mov.moved_by_user.first_name,
            "last_name": mov.moved_by_user.last_name,
            "email": mov.moved_by_user.email,
        }

    return base


# ===========================
# ENDPOINT LIST
# ===========================
@api.route("")
class MovementHistoryList(Resource):

    @login_required
    @role_required("admin", "manager","archivist")
    def get(self):
        from sqlalchemy import or_, desc

        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 20))
        except ValueError:
            page, per_page = 1, 20

        # Parámetros
        query_text = request.args.get("query", "").strip()
        record_file_id_param = request.args.get("record_file_id")

        origin_status_param = request.args.get("origin_status")
        destination_status_param = request.args.get("destination_status")

        moved_after = _parse_datetime(request.args.get("moved_after"))
        moved_before = _parse_datetime(request.args.get("moved_before"))

        # Base query
        q = MovementHistory.query.filter(MovementHistory.deleted_at.is_(None))

        # ==============================
        # 🔍 Buscador por referencia / número de expediente
        # ==============================
        if query_text:
            like = f"%{query_text}%"
            q = q.join(RecordFile).filter(
                or_(
                    RecordFile.reference_code.ilike(like),
                    RecordFile.file_number.ilike(like),
                )
            )

        # ==============================
        # 🎯 Filtros simples
        # ==============================
        if record_file_id_param:
            q = q.filter(MovementHistory.record_file_id == record_file_id_param)

        # ORIGIN STATUS
        if origin_status_param in ALLOWED_STATUSES:
            q = q.filter(MovementHistory.origin_status == origin_status_param)

        # DESTINATION STATUS
        if destination_status_param in ALLOWED_STATUSES:
            q = q.filter(MovementHistory.destination_status == destination_status_param)

        # ==============================
        # 📅 Filtros de fecha (movido desde / hasta)
        # ==============================
        if moved_after:
            q = q.filter(MovementHistory.moved_at >= moved_after)

        if moved_before:
            q = q.filter(MovementHistory.moved_at <= moved_before)

        # ==============================
        # 📌 Ordenamiento
        # ==============================
        q = q.order_by(
            desc(MovementHistory.moved_at),
            desc(MovementHistory.id),
        )

        # ==============================
        # 📦 Paginación
        # ==============================
        paginated = q.paginate(page=page, per_page=per_page, error_out=False)

        # ==============================
        # 📤 Respuesta
        # ==============================
        return {
            "message": "Movimientos obtenidos correctamente.",
            "movements": [_serialize_movement(m) for m in paginated.items],
            "pagination": {
                "total": paginated.total,
                "pages": paginated.pages,
                "current_page": paginated.page,
                "per_page": paginated.per_page,
                "has_next": paginated.has_next,
                "has_prev": paginated.has_prev,
                "next_page": paginated.next_num if paginated.has_next else None,
                "prev_page": paginated.prev_num if paginated.has_prev else None,
            }
        }, 200


    # ===========================
    # POST (Crear movimiento)
    # ===========================
    @login_required
    @role_required("admin", "manager","archivist")
    def post(self):
        schema = MovementHistoryCreateSchema()

        try:
            payload = request.get_json() or {}
            payload.pop("origin_status", None)  # Nunca lo aceptamos del cliente
            payload.pop("moved_by_user_id", None)
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        record_file_id = data["record_file_id"]
        destination_status = data["destination_status"]
        description = data.get("description")

        rf = RecordFile.query.get(record_file_id)
        if not rf or rf.deleted_at is not None:
            return {"message": "El expediente no existe o está eliminado."}, 400

        origin_status = rf.availability_status

        # No se puede mover si está prestado
        if origin_status == "on_loan":
            return {
                "message": "El expediente está prestado y no puede moverse.",
                "current_availability_status": origin_status,
            }, 400

        # Validar destino permitido
        if destination_status not in ALLOWED_STATUSES:
            return {
                "message": "El estado de destino no es válido.",
                "allowed": ALLOWED_STATUSES,
            }, 400

        # No mover al mismo estado
        if origin_status == destination_status:
            return {"message": "El estado de origen y destino no pueden ser iguales."}, 400

        # Fecha del movimiento
        if payload.get("moved_at"):
            moved_at_val = _parse_datetime(payload["moved_at"])
            if not moved_at_val:
                return {"message": "El formato de 'moved_at' no es válido."}, 400
        else:
            moved_at_val = datetime.utcnow()

        # Crear movimiento
        mov = MovementHistory(
            record_file_id=record_file_id,
            moved_by_user_id=current_user.id,
            description=description,
            origin_status=origin_status,
            destination_status=destination_status,
            moved_at=moved_at_val,
        )

        # Actualizar expediente
        rf.availability_status = destination_status

        if destination_status == "under_review":
            rf.last_preservation_date = moved_at_val.date().isoformat()

        if destination_status == "available":
            rf.last_fund_date = moved_at_val.date().isoformat()

        db.session.add(mov)

        try:
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": "Error al guardar movimiento.", "error": str(e)}, 500

        return {
            "message": "Movimiento creado correctamente.",
            "movement": _serialize_movement(mov, record_file=rf),
        }, 201


# ===========================
# DETALLE / PUT / DELETE
# ===========================
@api.route("/<int:movement_id>")
class MovementHistoryDetail(Resource):

    @login_required
    @role_required("admin", "manager","archivist")
    def get(self, movement_id: int):
        mov = MovementHistory.query.get(movement_id)
        if not mov or mov.deleted_at is not None:
            return {"message": "Movimiento no encontrado."}, 404

        return {
            "message": "Movimiento obtenido correctamente.",
            "movement": _serialize_movement(mov),
        }, 200

    @login_required
    @role_required("admin", "manager","archivist")
    def put(self, movement_id: int):

        schema = MovementHistoryUpdateSchema()

        try:
            payload = request.get_json() or {}
            payload.pop("origin_status", None)
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        mov = MovementHistory.query.get(movement_id)
        if not mov or mov.deleted_at is not None:
            return {"message": "Movimiento no encontrado."}, 404

        rf = mov.record_file

        old_dest = mov.destination_status

        # Actualizar descripción
        if "description" in data:
            mov.description = data["description"]

        # Actualizar destino
        if "destination_status" in data:
            new_dest = data["destination_status"]

            if new_dest not in ALLOWED_STATUSES:
                return {"message": "Estado de destino inválido."}, 400

            if new_dest == mov.origin_status:
                return {"message": "El destino no puede ser igual al origen."}, 400

            mov.destination_status = new_dest

            # Reaplicar efectos
            rf.availability_status = new_dest

            if new_dest == "under_review":
                rf.last_preservation_date = datetime.utcnow().date().isoformat()

            if new_dest == "available":
                rf.last_fund_date = datetime.utcnow().date().isoformat()

        # Actualizar fecha
        if "moved_at" in payload and payload["moved_at"]:
            parsed = _parse_datetime(payload["moved_at"])
            if not parsed:
                return {"message": "Fecha inválida."}, 400
            mov.moved_at = parsed

        try:
            mov.updated_at = db.func.now()
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": "Error al actualizar movimiento.", "error": str(e)}, 500

        return {
            "message": "Movimiento actualizado correctamente.",
            "movement": _serialize_movement(mov, record_file=rf),
        }, 200

    @login_required
    @role_required("admin", "manager","archivist")
    def delete(self, movement_id: int):

        mov = MovementHistory.query.get(movement_id)
        if not mov or mov.deleted_at is not None:
            return {"message": "Movimiento no encontrado."}, 404

        mov.deleted_at = db.func.now()

        db.session.commit()

        return {"message": "Movimiento eliminado correctamente."}, 200
