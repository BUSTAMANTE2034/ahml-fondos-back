"""
Esquemas de Clave de Catálogo (CatalogKey) para AHML Fondos.

Validan y serializan la información de las claves de catálogo
en las solicitudes y respuestas de la API.
"""

from marshmallow import Schema, fields, validate, ValidationError


class CatalogKeyBaseSchema(Schema):
    """Esquema base con los campos comunes de la clave de catálogo."""

    id = fields.Int(dump_only=True)
    user_id = fields.Int(dump_only=True)  # se asigna desde el backend según el usuario autenticado

    entity_type = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=50),
        error_messages={
            "required": "El tipo de entidad es obligatorio.",
            "null": "El tipo de entidad no puede ser nulo.",
        },
    )
    key = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=255),
        error_messages={
            "required": "La clave de catálogo es obligatoria.",
            "null": "La clave de catálogo no puede ser nula.",
        },
    )
    name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=255),
        error_messages={
            "required": "El nombre es obligatorio.",
            "null": "El nombre no puede ser nulo.",
        },
    )
    description = fields.Str(required=False)
    is_active = fields.Bool(dump_only=True)

    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)


class CatalogKeyCreateSchema(CatalogKeyBaseSchema):
    """Esquema para creación de una clave de catálogo."""

    # permitir enviar el estado desde el cliente
    is_active = fields.Bool(load_default=True)


class CatalogKeyUpdateSchema(Schema):
    """Esquema para actualizar parcialmente una clave de catálogo."""

    id = fields.Int(
        required=True,
        error_messages={"required": "El identificador de la clave es obligatorio."},
    )
    entity_type = fields.Str(
        validate=validate.Length(min=1, max=50),
        error_messages={"validator_failed": "El tipo de entidad no es válido."},
    )
    key = fields.Str(
        validate=validate.Length(min=1, max=255),
        error_messages={"validator_failed": "La clave debe tener entre 1 y 255 caracteres."},
    )
    name = fields.Str(
        validate=validate.Length(min=1, max=255),
        error_messages={"validator_failed": "El nombre debe tener entre 1 y 255 caracteres."},
    )
    description = fields.Str()
    is_active = fields.Bool()
    updated_at = fields.DateTime(dump_only=True)


class CatalogKeyResponseSchema(CatalogKeyBaseSchema):
    """Esquema para respuestas de clave de catálogo."""
    pass
