"""
Esquemas de Tipología documental para AHML Fondos.

Validan y serializan la información de las tipologías que se pueden asociar
a los expedientes.
"""

from marshmallow import Schema, fields, validate


class TypologyBaseSchema(Schema):
    """Esquema base con los campos comunes de la tipología."""

    id = fields.Int(dump_only=True)
    user_id = fields.Int(dump_only=True)

    name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=255),
        error_messages={
            "required": "El nombre de la tipología es obligatorio.",
        },
    )
    description = fields.Str(required=False)
    is_active = fields.Bool(dump_only=True)

    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)


class TypologyCreateSchema(TypologyBaseSchema):
    """Esquema para creación de tipologías documentales."""
    pass


class TypologyUpdateSchema(Schema):
    """Esquema para actualización parcial de una tipología."""

    id = fields.Int(required=True, error_messages={"required": "El ID de la tipología es obligatorio."})
    name = fields.Str(validate=validate.Length(min=1, max=255))
    description = fields.Str()
    is_active = fields.Bool()
    updated_at = fields.DateTime(dump_only=True)


class TypologyResponseSchema(TypologyBaseSchema):
    """Esquema para respuestas de tipologías."""
    pass
