"""
Esquemas de Revisión / Diagnóstico de Expedientes para AHML Fondos.

Una revisión puede tener múltiples conceptos/detalles asociados,
pero una sola observación general.
"""

from marshmallow import Schema, fields, validate
from app.schemas.user import UserBaseSchema
from app.schemas.record_file import RecordFileBaseSchema
from app.schemas.diagnosis_catalog import DiagnosisCatalogBaseSchema

class RecordDiagnosisBaseSchema(Schema):
    """Esquema base para una revisión de expediente."""

    id = fields.Int(dump_only=True)

    record_file_id = fields.Int(
        required=True,
        error_messages={
            "required": "El expediente es obligatorio para la revisión.",
        },
    )

    user_id = fields.Int(dump_only=True)

    revision_date = fields.DateTime(dump_only=True)

    observations = fields.Str(required=False)

    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)


class RecordDiagnosisCreateSchema(RecordDiagnosisBaseSchema):
    """
    Esquema para crear una revisión.

    diagnosis_catalog_ids:
    Lista de IDs del catálogo seleccionados en la revisión.
    """

    diagnosis_catalog_ids = fields.List(
        fields.Int(),
        required=True,
        validate=validate.Length(min=1),
        error_messages={
            "required": "Debe seleccionarse al menos un concepto de diagnóstico.",
        },
    )
    


class RecordDiagnosisResponseSchema(RecordDiagnosisBaseSchema):
    """Esquema de respuesta para revisiones."""

    # diagnosis_catalog_ids = fields.List(fields.Int(), dump_only=True)
    record_file = fields.Nested(
        RecordFileBaseSchema,
        dump_only=True,
        allow_none=True
    )

    user = fields.Nested(
        UserBaseSchema,
        dump_only=True,
        allow_none=True
    )

    diagnosis_catalog = fields.List(
        fields.Nested(DiagnosisCatalogBaseSchema),
        dump_only=True
    )
    
