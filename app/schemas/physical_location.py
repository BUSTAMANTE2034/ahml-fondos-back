from marshmallow import Schema, fields, validate


class PhysicalLocationBaseSchema(Schema):
    """Esquema base con los campos comunes de una ubicación física."""

    id = fields.Int(dump_only=True)
    code = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=50),
        error_messages={"required": "El código de la ubicación física es obligatorio."}
    )
    description = fields.Str(
        allow_none=True,
        validate=validate.Length(max=255)
    )
    user_id = fields.Int(dump_only=True)
    is_active = fields.Bool(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)


class PhysicalLocationCreateSchema(PhysicalLocationBaseSchema):
    """Esquema para creación de ubicaciones físicas."""
    pass


class PhysicalLocationUpdateSchema(Schema):
    """Esquema para actualización parcial de una ubicación física."""
    id = fields.Int(required=True, error_messages={"required": "El ID es obligatorio."})
    code = fields.Str(validate=validate.Length(min=1, max=50))
    description = fields.Str(allow_none=True, validate=validate.Length(max=255))
    is_active = fields.Bool()
    updated_at = fields.DateTime(dump_only=True)


class PhysicalLocationResponseSchema(PhysicalLocationBaseSchema):
    """Esquema para respuesta de ubicación física."""
    pass
