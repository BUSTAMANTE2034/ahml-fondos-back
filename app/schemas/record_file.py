# app/schemas/record_file.py
from marshmallow import Schema, fields, validate

class RecordFileBaseSchema(Schema):
    id = fields.Int(dump_only=True)
    reference_code = fields.Str(dump_only=True)

    subject = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=255),
    )
    file_number = fields.Str(validate=validate.Length(max=50))

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

    box_number = fields.Str(validate=validate.Length(max=50))
    page_count = fields.Int(allow_none=True)

    file_date = fields.Date(allow_none=True)
    last_preservation_date = fields.Date(allow_none=True)
    last_fund_date = fields.Date(allow_none=True)

    deterioration_status_id = fields.Int(allow_none=True)

    user_id = fields.Int(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)

    # para crear/actualizar
    typology_ids = fields.List(fields.Int(), required=False)


class RecordFileCreateSchema(RecordFileBaseSchema):
    # no agregamos nada extra, solo reutilizamos
    pass


class RecordFileUpdateSchema(Schema):
    id = fields.Int(required=True)

    subject = fields.Str(validate=validate.Length(min=1, max=255))
    file_number = fields.Str(validate=validate.Length(max=50))
    sensitive_data = fields.Bool()
    comments = fields.Str()
    availability_status = fields.Str(
        validate=validate.OneOf(["available", "unavailable", "under_review", "on_loan"])
    )

    fund_id = fields.Int(allow_none=True)
    section_id = fields.Int(allow_none=True)
    series_id = fields.Int(allow_none=True)
    location_id = fields.Int(allow_none=True)

    box_number = fields.Str(validate=validate.Length(max=50))
    page_count = fields.Int(allow_none=True)

    file_date = fields.Date(allow_none=True)
    last_preservation_date = fields.Date(allow_none=True)
    last_fund_date = fields.Date(allow_none=True)

    deterioration_status_id = fields.Int(allow_none=True)

    typology_ids = fields.List(fields.Int(), required=False)

    updated_at = fields.DateTime(dump_only=True)


class RecordFileResponseSchema(RecordFileBaseSchema):
    """OJO: aquí ya NO declaramos user, fund, section... porque los arma el endpoint."""
    pass
