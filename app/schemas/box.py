from marshmallow import Schema, fields, validate
from app.schemas.physical_location import PhysicalLocationResponseSchema


class BoxBaseSchema(Schema):
    """Esquema base para Box."""

    id = fields.Int(dump_only=True)
    box_number = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=50),
        error_messages={"required": "El número de caja es obligatorio."}
    )
    physical_location_id = fields.Int(required=True)
    description = fields.Str(allow_none=True, validate=validate.Length(max=255))
    user_id = fields.Int(dump_only=True)
    is_active = fields.Bool(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)

    # relación anidada opcional
    physical_location = fields.Nested(PhysicalLocationResponseSchema, dump_only=True)


class BoxCreateSchema(BoxBaseSchema):
    """Esquema para crear una caja."""
    pass


class BoxUpdateSchema(Schema):
    """Esquema para actualizar parcialmente una caja."""

    id = fields.Int(required=True, error_messages={"required": "El ID es obligatorio."})
    box_number = fields.Str(validate=validate.Length(min=1, max=50))
    physical_location_id = fields.Int()
    description = fields.Str(allow_none=True, validate=validate.Length(max=255))
    is_active = fields.Bool()
    updated_at = fields.DateTime(dump_only=True)


class BoxResponseSchema(BoxBaseSchema):
    """Esquema de respuesta para una caja."""
    pass
