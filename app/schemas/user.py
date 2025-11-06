"""
User schemas for AHML Fondos application.

Defines Marshmallow schemas for validating and serializing user data
in API requests and responses. Ensures proper data integrity for creation,
update, and response handling.
"""

from marshmallow import Schema, fields, validate, validates_schema, ValidationError


# Base Schema
class UserBaseSchema(Schema):
    """Base schema for user data shared across operations."""

    employee_id = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=20),
        error_messages={
            "required": "El número de empleado es obligatorio.",
            "validator_failed": "El número de empleado debe tener entre 1 y 20 caracteres.",
        },
    )
    first_name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=100),
        error_messages={"required": "El nombre es obligatorio."},
    )
    last_name = fields.Str(
        required=False,
        validate=validate.Length(max=100),
    )
    email = fields.Email(
        required=True,
        error_messages={
            "required": "El correo electrónico es obligatorio.",
            "invalid": "El formato del correo electrónico no es válido.",
        },
    )
    is_active = fields.Bool(dump_only=True)
    role = fields.Str(dump_only=True)
    first_login = fields.Bool(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)


# Create Schema
class UserCreateSchema(Schema):
    employee_id = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=20),
        error_messages={
            "required": "El número de empleado es obligatorio.",
        },
    )
    first_name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=100),
        error_messages={
            "required": "El nombre es obligatorio.",
        },
    )
    last_name = fields.Str(required=False, validate=validate.Length(max=100))
    email = fields.Email(
        required=True,
        error_messages={
            "required": "El correo electrónico es obligatorio.",
            "invalid": "El formato del correo electrónico no es válido.",
        },
    )
    # ya NO pedimos password aquí
    role = fields.Str(
        required=False,
        validate=validate.OneOf(["admin", "manager", "archivist", "visitor"]),
        load_default="visitor",
    )
    first_login = fields.Bool(load_default=True)

    @validates_schema
    def validate_passwords_match(self, data, **_):
        """Ensure password and confirmation match."""
        if data.get("password") != data.get("password_confirmation"):
            raise ValidationError(
                {"password_confirmation": ["Las contraseñas no coinciden."]}
            )


# Update Schema
class UserUpdateSchema(Schema):
    """Schema for user update requests (partial updates allowed)."""

    id = fields.Int(required=True, error_messages={"required": "El ID de usuario es obligatorio."})
    employee_id = fields.Str(validate=validate.Length(min=1, max=20))
    first_name = fields.Str(validate=validate.Length(min=1, max=100))
    last_name = fields.Str(validate=validate.Length(max=100))
    email = fields.Email(error_messages={"invalid": "El formato del correo electrónico no es válido."})
    password = fields.Str(validate=validate.Length(min=8, max=100))
    password_confirmation = fields.Str()
    role = fields.Str(
        validate=validate.OneOf(["admin", "manager", "archivist", "visitor"]),
        error_messages={
            "validator_failed": "El rol debe ser uno de: admin, manager, archivist, visitor.",
        },
    )
    is_active = fields.Bool()
    first_login = fields.Bool()

    @validates_schema
    def validate_passwords_match(self, data, **_):
        """Ensure both password fields match when present."""
        if data.get("password") and data.get("password_confirmation"):
            if data["password"] != data["password_confirmation"]:
                raise ValidationError(
                    {"password_confirmation": ["Las contraseñas no coinciden."]}
                )
        elif data.get("password") or data.get("password_confirmation"):
            raise ValidationError(
                {
                    "password": ["La contraseña y la confirmación son obligatorias cuando se actualiza la contraseña."],
                    "password_confirmation": ["La contraseña y la confirmación son obligatorias cuando se actualiza la contraseña."],
                }
            )


# Response Schema
class UserResponseSchema(UserBaseSchema):
    """Schema for user responses (output)."""

    id = fields.Int(dump_only=True)
    role = fields.Str(dump_only=True)
    last_login = fields.DateTime(dump_only=True)
