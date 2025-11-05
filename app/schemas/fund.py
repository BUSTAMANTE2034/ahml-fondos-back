"""
Esquemas de Fondo (Fund) para AHML Fondos.

Validan y serializan la información de los fondos documentales
en las solicitudes y respuestas de la API.
"""

from marshmallow import Schema, fields, validate


class FundBaseSchema(Schema):
    """Esquema base con los campos comunes del fondo."""

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
            "required": "El nombre del fondo es obligatorio.",
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


class FundCreateSchema(FundBaseSchema):
    """Esquema para creación de fondos documentales."""

    # si quieres permitir que el frontend lo mande:
    is_active = fields.Bool(load_default=True)


class FundUpdateSchema(Schema):
    """Esquema para actualización parcial de un fondo."""

    id = fields.Int(required=True, error_messages={"required": "El ID del fondo es obligatorio."})
    catalog_key_id = fields.Int(allow_none=True)
    name = fields.Str(validate=validate.Length(min=1, max=255))
    acronym = fields.Str(validate=validate.Length(max=50))
    start_date = fields.Date(allow_none=True)
    end_date = fields.Date(allow_none=True)
    is_active = fields.Bool()
    updated_at = fields.DateTime(dump_only=True)


class FundResponseSchema(FundBaseSchema):
    """Esquema para respuestas de fondos."""
    pass
