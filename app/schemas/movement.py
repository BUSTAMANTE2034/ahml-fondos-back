"""
Schemas para el historial de movimientos de expedientes (MovementHistory).
Validan creación, actualización y respuesta de los movimientos.
"""

from marshmallow import Schema, fields, validate

# NUEVO: valores que maneja el RecordFile
ALLOWED_STATUSES = ["available", "under_review", "unavailable"]


class MovementHistoryBaseSchema(Schema):
    """Esquema base de un movimiento de expediente."""

    id = fields.Int(dump_only=True)

    record_file_id = fields.Int(
        required=True,
        error_messages={
            "required": "El ID del expediente es obligatorio.",
        },
    )

    moved_by_user_id = fields.Int(dump_only=True)

    description = fields.Str(required=False)

    # YA NO SE USA en POST, pero aceptamos en PUT opcional
    origin_status = fields.Str(
        required=False,
        validate=validate.OneOf(ALLOWED_STATUSES),
        error_messages={
            "validator_failed": "El estado de origen no es válido.",
        },
    )

    destination_status = fields.Str(
        required=False,
        validate=validate.OneOf(ALLOWED_STATUSES),
        error_messages={
            "validator_failed": "El estado de destino no es válido.",
        },
    )

    # Ahora permitimos mandar moved_at en POST y PUT
    moved_at = fields.DateTime(required=False)

    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)


class MovementHistoryCreateSchema(MovementHistoryBaseSchema):
    """Esquema para crear un movimiento."""

    # destination_status obligatorio
    destination_status = fields.Str(
        required=True,
        validate=validate.OneOf(ALLOWED_STATUSES),
        error_messages={
            "required": "El estado de destino es obligatorio.",
            "validator_failed": "El estado de destino no es válido.",
        },
    )

    # origin_status se ignorará, pero lo permitimos en el cuerpo si llega
    origin_status = fields.Str(required=False)


class MovementHistoryUpdateSchema(Schema):
    """Esquema para actualizar un movimiento."""

    # YA NO pedimos el ID en el body
    description = fields.Str()

    origin_status = fields.Str(
        validate=validate.OneOf(ALLOWED_STATUSES),
        error_messages={"validator_failed": "El estado de origen no es válido."},
    )

    destination_status = fields.Str(
        validate=validate.OneOf(ALLOWED_STATUSES),
        error_messages={"validator_failed": "El estado de destino no es válido."},
    )

    moved_at = fields.DateTime(required=False)

    deleted_at = fields.DateTime(required=False)
    updated_at = fields.DateTime(dump_only=True)


class MovementHistoryResponseSchema(MovementHistoryBaseSchema):
    """Esquema de salida para movimientos."""
    pass
