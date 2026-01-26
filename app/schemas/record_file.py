# app/schemas/record_file.py
from marshmallow import Schema, fields, validate

class RecordFileBaseSchema(Schema):
    id = fields.Int(dump_only=True)
    reference_code = fields.Str(dump_only=True)
    previous_reference_code = fields.Str(
        allow_none=True,
        validate=validate.Length(max=255)
    )


    subject = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=1500),
    )
    file_number = fields.Str(dump_only=True)

    sensitive_data = fields.Bool(load_default=False)
    comments = fields.Str()

    availability_status = fields.Str(
        load_default="available",
        validate=validate.OneOf(["available", "unavailable", "under_review", "on_loan"]),
    )

    fund_id = fields.Int(allow_none=True)
    section_id = fields.Int(allow_none=True)
    series_id = fields.Int(allow_none=True)
    location_id = fields.Int(allow_none=True)
    
    box_id = fields.Int(allow_none=True)

    # LEGACY → SOLO LECTURA
    box_number = fields.Str(dump_only=True)
    page_count = fields.Int(allow_none=True)
    document_sizes = fields.Str(
        allow_none=True,
        validate=validate.Length(max=500)
    )

    file_date = fields.Date(allow_none=True)
    last_preservation_date = fields.Date(allow_none=True)
    last_fund_date = fields.Date(allow_none=True)

    deterioration_status_id = fields.Int(allow_none=True)

    # 🔐 auditoría (SOLO LECTURA)
    user_id = fields.Int(dump_only=True)
    updated_by_id = fields.Int(dump_only=True)
    deleted_by_id = fields.Int(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)

    # para crear/actualizar
    typology_ids = fields.List(fields.Int(), required=False)


from marshmallow import Schema, fields, validate, validates_schema, ValidationError

class RecordFileCreateSchema(RecordFileBaseSchema):

    # -------- OBLIGATORIOS --------
    fund_id = fields.Int(
        required=True,
        allow_none=False,
        error_messages={"required": "El fondo es obligatorio."},
    )

    section_id = fields.Int(
        required=True,
        allow_none=False,
        error_messages={"required": "La sección es obligatoria."},
    )

    series_id = fields.Int(
        required=True,
        allow_none=False,
        error_messages={"required": "La serie es obligatoria."},
    )

    location_id = fields.Int(
        required=True,
        allow_none=False,
        error_messages={"required": "La ubicación es obligatoria."},
    )

    box_id = fields.Int(
        required=True,
        allow_none=False,
        error_messages={"required": "La caja es obligatoria."},
    )

    deterioration_status_id = fields.Int(
        required=True,
        allow_none=False,
        error_messages={"required": "El estado de deterioro es obligatorio."},
    )

    subject = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=1500),
        error_messages={"required": "El asunto es obligatorio."},
    )

    previous_reference_code = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=255),
        error_messages={"required": "La referencia anterior es obligatoria."},
    )

    document_sizes = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=500),
        error_messages={"required": "Debes seleccionar al menos un tamaño de documento."},
    )

    typology_ids = fields.List(
        fields.Int(),
        required=True,
        validate=validate.Length(min=1),
        error_messages={"required": "Debes seleccionar al menos una tipología."},
    )


class RecordFileUpdateSchema(Schema):
    id = fields.Int(required=True)

    subject = fields.Str(validate=validate.Length(min=1, max=1500))
    previous_reference_code = fields.Str(validate=validate.Length(max=255))
    file_number = fields.Str(dump_only=True)
    sensitive_data = fields.Bool()
    comments = fields.Str()
    availability_status = fields.Str(
        validate=validate.OneOf(["available", "unavailable", "under_review", "on_loan"])
    )

    fund_id = fields.Int(allow_none=True)
    section_id = fields.Int(allow_none=True)
    series_id = fields.Int(allow_none=True)
    location_id = fields.Int(allow_none=True)
    
    box_id = fields.Int(allow_none=True)
    page_count = fields.Int(allow_none=True)
    document_sizes = fields.Str(
        allow_none=True,
        validate=validate.Length(max=500)
    )
    

    file_date = fields.Date(allow_none=True)
    last_preservation_date = fields.Date(allow_none=True)
    last_fund_date = fields.Date(allow_none=True)

    deterioration_status_id = fields.Int(allow_none=True)

    typology_ids = fields.List(fields.Int(), required=False)

    updated_at = fields.DateTime(dump_only=True)


class RecordFileResponseSchema(RecordFileBaseSchema):
    """OJO: aquí ya NO declaramos user, fund, section... porque los arma el endpoint."""
    pass
