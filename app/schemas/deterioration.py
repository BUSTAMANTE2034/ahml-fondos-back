"""
Esquemas de Deterioro (Deterioration) para AHML Fondos.

Validan y serializan la información de los tipos/registros de deterioro
que se pueden asociar a los expedientes.
"""

from marshmallow import Schema, fields, validate


class DeteriorationBaseSchema(Schema):
    """Esquema base con los campos comunes del deterioro."""

    id = fields.Int(dump_only=True)
    user_id = fields.Int(dump_only=True)

    name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=255),
        error_messages={
            "required": "El nombre del deterioro es obligatorio.",
        },
    )
    description = fields.Str(required=False)

    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)


class DeteriorationCreateSchema(DeteriorationBaseSchema):
    """Esquema para creación de registros de deterioro."""
    pass


class DeteriorationUpdateSchema(Schema):
    """Esquema para actualización parcial de un registro de deterioro."""

    id = fields.Int(required=True, error_messages={"required": "El ID del deterioro es obligatorio."})
    name = fields.Str(validate=validate.Length(min=1, max=255))
    description = fields.Str()
    updated_at = fields.DateTime(dump_only=True)


class DeteriorationResponseSchema(DeteriorationBaseSchema):
    """Esquema para respuestas de deterioro."""
    pass
