"""
Esquemas de Catálogo de Diagnóstico para AHML Fondos.

Validan y serializan los conceptos y detalles utilizados
en la revisión técnica de expedientes.
"""

from marshmallow import Schema, fields, validate


class DiagnosisCatalogBaseSchema(Schema):
    """Esquema base con los campos comunes del catálogo de diagnóstico."""

    id = fields.Int(dump_only=True)

    concept = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=255),
        error_messages={
            "required": "El concepto de diagnóstico es obligatorio.",
        },
    )
    user_id = fields.Int(dump_only=True)

    detail = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=255),
        error_messages={
            "required": "El detalle del diagnóstico es obligatorio.",
        },
    )

    description = fields.Str(required=False)

    is_active = fields.Bool(dump_only=True)

    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)


class DiagnosisCatalogCreateSchema(DiagnosisCatalogBaseSchema):
    """Esquema para creación de registros del catálogo de diagnóstico."""
    pass


class DiagnosisCatalogUpdateSchema(Schema):
    """Esquema para actualización parcial del catálogo de diagnóstico."""

    id = fields.Int(
        required=True,
        error_messages={"required": "El ID del diagnóstico es obligatorio."},
    )
    user_id = fields.Int(dump_only=True)

    concept = fields.Str(validate=validate.Length(min=1, max=255))
    detail = fields.Str(validate=validate.Length(min=1, max=255))
    description = fields.Str()
    is_active = fields.Bool()

    updated_at = fields.DateTime(dump_only=True)


class DiagnosisCatalogResponseSchema(DiagnosisCatalogBaseSchema):
    """Esquema para respuestas del catálogo de diagnóstico."""
    pass
