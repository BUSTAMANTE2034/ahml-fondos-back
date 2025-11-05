"""
Esquemas de Series documentales para AHML Fondos.

Validan y serializan la información de las series que pertenecen a un fondo
y que pueden usar una clave de catálogo.
"""

from marshmallow import Schema, fields, validate


class SeriesBaseSchema(Schema):
    """Esquema base con los campos comunes de la serie documental."""

    id = fields.Int(dump_only=True)
    catalog_key_id = fields.Int(required=False, allow_none=True)
    fund_id = fields.Int(required=False, allow_none=True)
    user_id = fields.Int(dump_only=True)

    name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=255),
        error_messages={
            "required": "El nombre de la serie es obligatorio.",
        },
    )
    acronym = fields.Str(
        required=False,
        validate=validate.Length(max=50),
    )

    start_date = fields.Date(required=False, allow_none=True)
    end_date = fields.Date(required=False, allow_none=True)

    is_active = fields.Bool(dump_only=True)

    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)


class SeriesCreateSchema(SeriesBaseSchema):
    """Esquema para creación de series documentales."""

    is_active = fields.Bool(load_default=True)


class SeriesUpdateSchema(Schema):
    """Esquema para actualización parcial de una serie documental."""

    id = fields.Int(required=True, error_messages={"required": "El ID de la serie es obligatorio."})
    catalog_key_id = fields.Int(allow_none=True)
    fund_id = fields.Int(allow_none=True)
    name = fields.Str(validate=validate.Length(min=1, max=255))
    acronym = fields.Str(validate=validate.Length(max=50))
    start_date = fields.Date(allow_none=True)
    end_date = fields.Date(allow_none=True)
    is_active = fields.Bool()
    updated_at = fields.DateTime(dump_only=True)


class SeriesResponseSchema(SeriesBaseSchema):
    """Esquema para respuestas de series documentales."""
    pass
