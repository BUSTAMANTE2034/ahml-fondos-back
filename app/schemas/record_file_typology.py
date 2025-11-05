"""
Schemas para la relación RecordFile - Typology.

Validan los datos cuando se vincula una tipología a un expediente
y cuando se listan esas relaciones.
"""

from marshmallow import Schema, fields, validate


class RecordFileTypologyBaseSchema(Schema):
    """Esquema base de la relación expediente–tipología."""

    id = fields.Int(dump_only=True)

    record_file_id = fields.Int(
        required=True,
        error_messages={
            "required": "El ID del expediente es obligatorio.",
        },
    )
    typology_id = fields.Int(
        required=True,
        error_messages={
            "required": "El ID de la tipología es obligatorio.",
        },
    )

    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)


class RecordFileTypologyCreateSchema(RecordFileTypologyBaseSchema):
    """Esquema para crear una relación expediente–tipología."""
    #aceptar solo record_file_id y typology_id
    pass


class RecordFileTypologyUpdateSchema(Schema):
    """Esquema para actualizar una relación (normalmente solo soft delete)."""

    id = fields.Int(
        required=True,
        error_messages={"required": "El ID del registro es obligatorio."},
    )
    deleted_at = fields.DateTime()  #  marcarla como eliminada lógicamente
    # updated_at solo salida
    updated_at = fields.DateTime(dump_only=True)


class RecordFileTypologyResponseSchema(RecordFileTypologyBaseSchema):
    """Esquema de respuesta de la relación expediente–tipología."""
    pass
