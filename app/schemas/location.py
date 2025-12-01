"""
Esquemas de Ubicación (Location) para AHML Fondos.

Validan y serializan la información de las ubicaciones físicas
donde pueden almacenarse los expedientes.
"""

from marshmallow import Schema, fields, validate


class LocationBaseSchema(Schema):
    """Esquema base con los campos comunes de la ubicación."""

    id = fields.Int(dump_only=True)
    name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=255),
        error_messages={
            "required": "El nombre de la ubicación es obligatorio.",
        },
    )
    user_id = fields.Int(dump_only=True)
    is_active = fields.Bool(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)


class LocationCreateSchema(LocationBaseSchema):
    """Esquema para creación de ubicaciones."""
    pass


class LocationUpdateSchema(Schema):
    """Esquema para actualización parcial de una ubicación."""

    id = fields.Int(required=True, error_messages={"required": "El ID de la ubicación es obligatorio."})
    name = fields.Str(validate=validate.Length(min=1, max=255))
    is_active = fields.Bool()
    updated_at = fields.DateTime(dump_only=True)


class LocationResponseSchema(LocationBaseSchema):
    """Esquema para respuestas de ubicaciones."""
    pass
