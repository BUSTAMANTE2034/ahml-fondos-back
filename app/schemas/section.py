"""
Esquemas de Sección (Section) para AHML Fondos.

Validan y serializan la información de las secciones administrativas
en las solicitudes y respuestas de la API.
"""

from marshmallow import Schema, fields, validate


class SectionBaseSchema(Schema):
    """Esquema base con los campos comunes de la sección."""

    id = fields.Int(dump_only=True)
    catalog_key_id = fields.Int(
        required=False,
        allow_none=True,
        metadata={"description": "ID de la clave de catálogo asociada"},
    )
    user_id = fields.Int(dump_only=True)

    name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=255),
        error_messages={
            "required": "El nombre de la sección es obligatorio.",
        },
    )
    acronym = fields.Str(
        required=False,
        validate=validate.Length(max=50),
    )

    created_at = fields.DateTime(dump_only=True)
    start_date = fields.Date(required=False, allow_none=True)
    end_date = fields.Date(required=False, allow_none=True)
    is_active = fields.Bool(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)


class SectionCreateSchema(SectionBaseSchema):
    """Esquema para creación de secciones administrativas."""

    is_active = fields.Bool(load_default=True)


class SectionUpdateSchema(Schema):
    """Esquema para actualización parcial de una sección."""

    id = fields.Int(required=True, error_messages={"required": "El ID de la sección es obligatorio."})
    catalog_key_id = fields.Int(allow_none=True)
    name = fields.Str(validate=validate.Length(min=1, max=255))
    acronym = fields.Str(validate=validate.Length(max=50))
    start_date = fields.Date(allow_none=True)
    end_date = fields.Date(allow_none=True)
    is_active = fields.Bool()
    updated_at = fields.DateTime(dump_only=True)


class SectionResponseSchema(SectionBaseSchema):
    """Esquema para respuestas de secciones."""
    pass
