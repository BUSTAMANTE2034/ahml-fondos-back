"""
Schemas para el historial de movimientos de expedientes (MovementHistory).
Validan creación, actualización y respuesta de los movimientos.
"""

from marshmallow import Schema, fields, validate


# valores que manejas en el modelo
ALLOWED_STATUSES = ["archive", "review", "preservation", "restoration"]


class MovementHistoryBaseSchema(Schema):
    """Esquema base de un movimiento de expediente."""

    id = fields.Int(dump_only=True)

    record_file_id = fields.Int(
        required=True,
        error_messages={
            "required": "El ID del expediente es obligatorio.",
        },
    )
    moved_by_user_id = fields.Int(
        required=True,
        error_messages={
            "required": "El ID del usuario que realizó el movimiento es obligatorio.",
        },
    )

    description = fields.Str(required=False)

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

    moved_at = fields.DateTime(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)


class MovementHistoryCreateSchema(MovementHistoryBaseSchema):
    """Esquema para crear un registro de movimiento."""

    # aquí sí podemos exigir destination_status
    destination_status = fields.Str(
        required=True,
        validate=validate.OneOf(ALLOWED_STATUSES),
        error_messages={
            "required": "El estado de destino es obligatorio.",
            "validator_failed": "El estado de destino no es válido.",
        },
    )
    # origin_status puede venir en null si el expediente estaba “sin estado”


class MovementHistoryUpdateSchema(Schema):
    """Esquema para actualizar un movimiento (normalmente comentarios o soft delete)."""

    id = fields.Int(
        required=True,
        error_messages={"required": "El ID del movimiento es obligatorio."},
    )
    description = fields.Str()
    origin_status = fields.Str(
        validate=validate.OneOf(ALLOWED_STATUSES),
        error_messages={
            "validator_failed": "El estado de origen no es válido.",
        },
    )
    destination_status = fields.Str(
        validate=validate.OneOf(ALLOWED_STATUSES),
        error_messages={
            "validator_failed": "El estado de destino no es válido.",
        },
    )
    deleted_at = fields.DateTime()
    updated_at = fields.DateTime(dump_only=True)


class MovementHistoryResponseSchema(MovementHistoryBaseSchema):
    """Esquema de salida para movimientos."""
    pass
