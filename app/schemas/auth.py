"""Esquemas de autenticación para validar requests/responses."""

from marshmallow import Schema, fields, validate, validates_schema, ValidationError


class LoginSchema(Schema):
    """Schema para iniciar sesión."""

    email = fields.Email(
        required=True,
        error_messages={
            "required": "El correo electrónico es obligatorio.",
            "invalid": "Formato de correo electrónico no válido.",
        },
    )
    password = fields.Str(
        required=True,
        validate=validate.Length(min=8),
        error_messages={
            "required": "La contraseña es obligatoria.",
            "invalid": "La contraseña no es válida.",
        },
    )
    # antes: fields.Bool(default=False)
    # ahora:
    remember_me = fields.Bool(load_default=False)


class LoginResponseSchema(Schema):
    """Respuesta de inicio de sesión."""

    message = fields.Str(required=True)
    user = fields.Dict(required=True)
    # token = fields.Str()
    # expires_at = fields.DateTime()


class LogoutSchema(Schema):
    """Respuesta de cierre de sesión."""

    message = fields.Str(required=True)
    # aquí solo lo mandamos nosotros en la respuesta
    # antes: status = fields.Bool(default=True)
    # ahora:
    status = fields.Bool(dump_default=True)


# Si todavía tienes estos en el archivo, también hay que corregirlos:

class SignInSchema(Schema):
    """Schema para registro de usuario."""

    email = fields.Email(
        required=True,
        error_messages={
            "required": "El correo electrónico es obligatorio.",
            "invalid": "Formato de correo electrónico no válido.",
        },
    )
    password = fields.Str(
        required=True,
        validate=validate.Length(min=8, max=100),
        error_messages={
            "required": "La contraseña es obligatoria.",
            "invalid": "La contraseña no es válida.",
        },
    )
    password_confirmation = fields.Str(
        required=True,
        error_messages={
            "required": "La confirmación de contraseña es obligatoria.",
        },
    )
    first_name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=50),
        error_messages={
            "required": "El nombre es obligatorio.",
            "invalid": "El nombre no es válido.",
        },
    )
    last_name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=50),
        error_messages={
            "required": "El apellido es obligatorio.",
            "invalid": "El apellido no es válido.",
        },
    )
    terms_accepted = fields.Bool(
        required=True,
        validate=validate.Equal(True),
        error_messages={
            "required": "Debes aceptar los términos y condiciones.",
            "invalid": "Debes aceptar los términos y condiciones.",
        },
    )

    @validates_schema
    def validate_passwords_match(self, data, **kwargs):
        if data.get("password") != data.get("password_confirmation"):
            raise ValidationError(
                {"password_confirmation": ["Las contraseñas no coinciden."]}
            )


class SignInResponseSchema(Schema):
    """Respuesta de registro."""

    message = fields.Str(required=True)
    user = fields.Dict(required=True)
    # antes: verification_required = fields.Bool(default=False)
    # ahora:
    verification_required = fields.Bool(dump_default=False)
