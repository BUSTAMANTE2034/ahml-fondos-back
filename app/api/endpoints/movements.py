"""Endpoints de historial de movimientos de expedientes (JSON)."""

from datetime import datetime

from flask import request
from flask_login import login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.record_file import RecordFile
from app.models.movement import MovementHistory
from app.models.deterioration import Deterioration  # por si quieres anidar nombre
from app.schemas.movement import (
    MovementHistoryCreateSchema,
    MovementHistoryUpdateSchema,
    MovementHistoryResponseSchema,
)
from typing import Optional

from app.utils.security import role_required

api = Namespace("movement-history", description="Operaciones de historial de movimientos de expedientes")

# los mismos que definiste en el schema
ALLOWED_STATUSES = ["archive", "review", "preservation", "restoration"]


# Helpers
def _parse_datetime(dt_str: str):
    """Intenta parsear un datetime ISO 'YYYY-MM-DD HH:MM:SS' o 'YYYY-MM-DD'. Devuelve None si falla."""
    if not dt_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return None


def _get_last_movement(record_file_id: int):
    """Devuelve el último movimiento NO eliminado de un expediente."""
    return (
        MovementHistory.query
        .filter(
            MovementHistory.record_file_id == record_file_id,
            MovementHistory.deleted_at.is_(None),
        )
        .order_by(MovementHistory.moved_at.desc(), MovementHistory.id.desc())
        .first()
    )


def _serialize_movement(
    mov: MovementHistory,
    record_file: Optional[RecordFile] = None,
):
    """
    Serializa un movimiento incluyendo:
      - datos del expediente
      - datos del usuario que movió
      - deterioro del expediente
    """
    base = MovementHistoryResponseSchema().dump(mov)

    rf = record_file or mov.record_file


    base["record_file"] = (
        {
            "id": rf.id,
            "reference_code": rf.reference_code,
            "availability_status": rf.availability_status,
            "last_preservation_date": rf.last_preservation_date,
            "last_fund_date": rf.last_fund_date,
            "deterioration": (
                {
                    "deterioration_status_id": rf.deterioration_status_id,
                    "deterioration_name": rf.deterioration_status.name,
                    "deterioration_status_updated_at": rf.deterioration_status_updated_at,
                }
                if rf.deterioration_status
                else None
            ),
        }
        if rf
        else None
    )

    base["moved_by_user"] = (
        {
            "id": mov.moved_by_user.id,
            "first_name": mov.moved_by_user.first_name,
            "last_name": mov.moved_by_user.last_name,
            "email": mov.moved_by_user.email,
        }
        if mov.moved_by_user
        else None
    )

    return base


def _apply_record_file_side_effects(
    record_file: RecordFile,
    destination_status: str,
    movement_datetime: datetime,
):
    """
    Aplica las reglas sobre el expediente cuando se mueve:

    - Si va a review / preservation / restoration:
        availability_status = "under_review"
        last_preservation_date = movement_datetime.date()
    - Si va a archive:
        availability_status = "available"
        last_fund_date = movement_datetime.date()
    """
    if destination_status in ("review", "preservation", "restoration"):
        record_file.availability_status = "under_review"
        record_file.last_preservation_date = movement_datetime.date()
    elif destination_status == "archive":
        record_file.availability_status = "available"
        record_file.last_fund_date = movement_datetime.date()


# =========================================================
# Rutas
# =========================================================
@api.route("")
class MovementHistoryList(Resource):
    @login_required
    @role_required("admin", "manager")
    def get(self):
        """
        Lists movements of record files.

        Descripción:
            Obtiene una lista paginada de movimientos (no eliminados lógicamente),
            con opción de filtrar por expediente y por usuario que hizo el movimiento.

        Parámetros de consulta:
            - page (int, opcional): Número de página (por defecto 1).
            - per_page (int, opcional): Tamaño de página (por defecto 20).
            - record_file_id (int, opcional): Filtra por expediente.
            - moved_by_user_id (int, opcional): Filtra por usuario que movió.
            - destination_status (str, opcional): Filtra por estado destino.
            - origin_status (str, opcional): Filtra por estado origen.

        Respuestas:
            200: {
                "message": "Movimientos obtenidos correctamente.",
                "movements": [...],
                "pagination": {...}
            }
        """
        record_file_id_param = request.args.get("record_file_id")
        moved_by_user_id_param = request.args.get("moved_by_user_id")
        dest_status_param = request.args.get("destination_status")
        orig_status_param = request.args.get("origin_status")

        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 20))
        except ValueError:
            page = 1
            per_page = 20

        query = MovementHistory.query.filter(MovementHistory.deleted_at.is_(None))

        if record_file_id_param:
            try:
                rf_id = int(record_file_id_param)
                query = query.filter(MovementHistory.record_file_id == rf_id)
            except ValueError:
                pass

        if moved_by_user_id_param:
            try:
                u_id = int(moved_by_user_id_param)
                query = query.filter(MovementHistory.moved_by_user_id == u_id)
            except ValueError:
                pass

        if dest_status_param in ALLOWED_STATUSES:
            query = query.filter(MovementHistory.destination_status == dest_status_param)

        if orig_status_param in ALLOWED_STATUSES:
            query = query.filter(MovementHistory.origin_status == orig_status_param)

        query = query.order_by(MovementHistory.moved_at.desc())

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        items = paginated.items

        # para evitar N+1, vamos a ir serializando con el record_file ya cargado
        movements_serialized = [
            _serialize_movement(mov) for mov in items
        ]

        return {
            "message": "Movimientos obtenidos correctamente.",
            "movements": movements_serialized,
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
        Creates a movement for a record file.

        Descripción:
            Crea un nuevo movimiento de un expediente.
            Reglas:
              - El expediente debe existir y no estar eliminado.
              - El expediente debe tener availability_status = "available"
                salvo que el destino sea "archive" (permite regresar).
              - origin_status y destination_status no pueden ser iguales.
              - Si no se envía origin_status, se toma el destino del último movimiento.
              - Si SÍ se envía origin_status, debe coincidir con el destino del último movimiento.
              - Se actualiza el expediente según el destino:
                    * review/preservation/restoration -> availability = under_review,
                      last_preservation_date = moved_at
                    * archive -> availability = available,
                      last_fund_date = moved_at
              - moved_by_user_id se toma del usuario autenticado, no del payload.

        Cuerpo (JSON):
            - record_file_id (int, requerido)
            - description (str, opcional)
            - origin_status (str, opcional)
            - destination_status (str, requerido): uno de ["archive","review","preservation","restoration"]
            - moved_at (str, opcional, "YYYY-MM-DD" o "YYYY-MM-DD HH:MM:SS")

        Respuestas:
            201: Movimiento creado correctamente.
            400: Error de validación o reglas de negocio.
        """
        schema = MovementHistoryCreateSchema()
        try:
            payload = request.get_json() or {}
            # no aceptamos moved_by_user_id del cliente
            payload.pop("moved_by_user_id", None)
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        record_file_id = data["record_file_id"]
        destination_status = data["destination_status"]
        origin_status = data.get("origin_status")
        description = data.get("description")

        # expediente
        rf = RecordFile.query.get(record_file_id)
        if not rf or rf.deleted_at is not None:
            return {"message": "El expediente no existe o está eliminado."}, 400

        # último movimiento
        last_mov = _get_last_movement(record_file_id)

        # si no viene origin_status, tomar el del último movimiento
        if origin_status is None and last_mov:
            origin_status = last_mov.destination_status

        # si había un último movimiento, el origin_status debe coincidir
        if last_mov and origin_status and origin_status != last_mov.destination_status:
            return {
                "message": "El estado de origen no coincide con el último movimiento registrado.",
                "last_destination_status": last_mov.destination_status,
                "provided_origin_status": origin_status,
            }, 400

        # no puede moverse al mismo lugar
        if origin_status and destination_status and origin_status == destination_status:
            return {"message": "El estado de origen y destino no pueden ser iguales."}, 400

        # regla de disponibilidad:
        # si el expediente NO está available, solo permitimos si lo regresan a archive
        if rf.availability_status != "available" and destination_status != "archive":
            return {
                "message": "El expediente no está disponible para mover.",
                "current_availability_status": rf.availability_status,
            }, 400

        # moved_at
        moved_at_val = None
        if "moved_at" in payload and payload["moved_at"]:
            parsed = _parse_datetime(payload["moved_at"])
            if not parsed:
                return {"message": "El formato de 'moved_at' no es válido."}, 400
            moved_at_val = parsed
        else:
            moved_at_val = db.func.now()

        # crear movimiento
        mov = MovementHistory(
            record_file_id=record_file_id,
            moved_by_user_id=current_user.id if current_user.is_authenticated else None,
            description=description,
            origin_status=origin_status,
            destination_status=destination_status,
            moved_at=moved_at_val,
        )

        # aplicar efectos en el expediente
        _apply_record_file_side_effects(rf, destination_status, moved_at_val)

        db.session.add(mov)

        try:
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": "Error al guardar en base de datos.", "error": str(e)}, 500

        return {
            "message": "Movimiento creado correctamente.",
            "movement": _serialize_movement(mov, record_file=rf),
        }, 201


@api.route("/<int:movement_id>")
class MovementHistoryDetail(Resource):
    @login_required
    @role_required("admin", "manager")
    def get(self, movement_id: int):
        """
        Gets a movement by ID.

        Descripción:
            Obtiene un movimiento específico por su identificador,
            siempre que no esté eliminado lógicamente.

        Parámetros de ruta:
            - movement_id (int): ID del movimiento.

        Respuestas:
            200: Movimiento obtenido correctamente.
            404: Movimiento no encontrado.
        """
        mov = MovementHistory.query.get(movement_id)
        if not mov or mov.deleted_at is not None:
            return {"message": "Movimiento no encontrado."}, 404

        return {
            "message": "Movimiento obtenido correctamente.",
            "movement": _serialize_movement(mov),
        }, 200

    @login_required
    @role_required("admin", "manager")
    def put(self, movement_id: int):
        """
        Updates a movement.

        Descripción:
            Actualiza un movimiento ya registrado. Usos típicos:
              - cambiar la descripción
              - corregir la fecha de movimiento (moved_at)
              - excepcionalmente corregir origin/destination (se revalida)
            Si se cambia el destino, se vuelve a aplicar la regla sobre el expediente.

        Parámetros de ruta:
            - movement_id (int): ID del movimiento a actualizar.

        Cuerpo (JSON):
            - description (str, opcional)
            - origin_status (str, opcional)
            - destination_status (str, opcional)
            - moved_at (str, opcional, "YYYY-MM-DD" o "YYYY-MM-DD HH:MM:SS")

        Respuestas:
            200: Movimiento actualizado.
            400: Error de validación o reglas de negocio.
            404: Movimiento no encontrado.
        """
        schema = MovementHistoryUpdateSchema()
        try:
            payload = request.get_json() or {}
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        mov = MovementHistory.query.get(movement_id)
        if not mov or mov.deleted_at is not None:
            return {"message": "Movimiento no encontrado."}, 404

        rf = mov.record_file
        if not rf or rf.deleted_at is not None:
            return {"message": "El expediente asociado ya no existe o está eliminado."}, 400

        # guardamos los viejos para saber si hay que re-aplicar efecto
        old_dest = mov.destination_status

        # origin/destination
        if "origin_status" in data and data["origin_status"] is not None:
            if data["origin_status"] not in ALLOWED_STATUSES:
                return {"message": "El estado de origen no es válido."}, 400
            mov.origin_status = data["origin_status"]

        if "destination_status" in data and data["destination_status"] is not None:
            if data["destination_status"] not in ALLOWED_STATUSES:
                return {"message": "El estado de destino no es válido."}, 400
            # no permitir mismo origen/destino
            if mov.origin_status and mov.origin_status == data["destination_status"]:
                return {"message": "El estado de origen y destino no pueden ser iguales."}, 400
            mov.destination_status = data["destination_status"]

        if "description" in data:
            mov.description = data["description"]

        # moved_at opcional
        if "moved_at" in payload and payload["moved_at"]:
            parsed = _parse_datetime(payload["moved_at"])
            if not parsed:
                return {"message": "El formato de 'moved_at' no es válido."}, 400
            mov.moved_at = parsed
        else:
            # si no mandan nada, dejamos el que tenía
            parsed = mov.moved_at

        # si cambió el destino, hay que re-aplicar al expediente
        if mov.destination_status != old_dest:
            _apply_record_file_side_effects(rf, mov.destination_status, mov.moved_at)

        try:
            mov.updated_at = db.func.now()
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": "Error al guardar en base de datos.", "error": str(e)}, 500

        return {
            "message": "Movimiento actualizado correctamente.",
            "movement": _serialize_movement(mov, record_file=rf),
        }, 200

    @login_required
    @role_required("admin", "manager")
    def delete(self, movement_id: int):
        """
        Soft deletes a movement.

        Descripción:
            Realiza un borrado lógico del movimiento.

        Parámetros de ruta:
            - movement_id (int): ID del movimiento.

        Respuestas:
            200: Movimiento eliminado.
            404: No encontrado.
        """
        mov = MovementHistory.query.get(movement_id)
        if not mov or mov.deleted_at is not None:
            return {"message": "Movimiento no encontrado."}, 404

        mov.deleted_at = db.func.now()

        db.session.commit()

        return {"message": "Movimiento eliminado correctamente."}, 200
