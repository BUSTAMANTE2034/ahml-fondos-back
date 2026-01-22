"""Endpoints de autenticación.

Define endpoints para autenticación de usuarios y manejo de sesión.
Implementa validación con schemas para requests y responses.
"""

from flask import request
from flask_login import login_user, logout_user, login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from app.utils.security import role_required, generate_temp_password
from app.services.email_service import send_temp_password_email,send_recovered_password_email

from app.extensions import bcrypt, db
from app.models.user import User
from app.schemas.auth import (
    LoginSchema,
    LoginResponseSchema,
    LogoutSchema,
    ChangePasswordSchema,
    RecoverPasswordSchema
)
from app.schemas.user import UserResponseSchema

# Namespace de la API
api = Namespace("auth", description="Operaciones de autenticación")


@api.route("/login")
class Login(Resource):
    """Recurso para inicio de sesión."""

    def post(self):
        """Procesa el inicio de sesión de un usuario."""
        schema = LoginSchema()
        try:
            payload = request.get_json() or {}
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        email = data["email"]
        password = data["password"]
        remember_me = data.get("remember_me", False)

        user = User.query.filter_by(email=email).first()
        if not user:
            return LoginResponseSchema().dump({"message": "El usuario no existe."}), 404

        if bcrypt.check_password_hash(user.password, password):
            # if user.first_login:
            #     user.first_login = False
            # Actualiza último acceso
            user.last_login =  db.func.now()
            db.session.commit()

            # Inicia sesión
            login_user(user, remember=remember_me)

            response_data = {
                "message": "Usuario autenticado.",
                "user": UserResponseSchema().dump(user),
            }
            try:
                return LoginResponseSchema().dump(response_data), 200
            except ValidationError as err:
                return {"message": "Error de validación.", "errors": err.messages}, 400

        return LoginResponseSchema().dump({"message": "Contraseña incorrecta."}), 401


@api.route("/logout")
class Logout(Resource):
    """Recurso para cierre de sesión."""

    # @login_required
    def delete(self):
        """Cierra la sesión del usuario autenticado."""
        logout_user()
        try:
            return (
                LogoutSchema().dump(
                    {"message": "Sesión cerrada correctamente.", "status": True}
                ),
                200,
            )
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400


@api.route("/me")
class Me(Resource):
    """Devuelve el usuario autenticado actual."""

    @login_required
    def get(self):
        return UserResponseSchema().dump(current_user), 200


@api.route("/change-password")
class ChangePassword(Resource):
    """Permite al usuario autenticado cambiar su propia contraseña."""

    @login_required
    def post(self):
        schema = ChangePasswordSchema()
        try:
            payload = request.get_json() or {}
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        current_password = data["current_password"]
        new_password = data["new_password"]
        new_password_confirmation = data["new_password_confirmation"]

        if not bcrypt.check_password_hash(current_user.password, current_password):
            return {"message": "La contraseña actual es incorrecta."}, 400

        if new_password != new_password_confirmation:
            return {
                "message": "Las contraseñas no coinciden.",
                "errors": {
                    "new_password_confirmation": [
                        "La confirmación no coincide con la nueva contraseña."
                    ]
                },
            }, 400

        current_user.password = bcrypt.generate_password_hash(new_password).decode("utf-8")
        current_user.first_login = False
        current_user.updated_at = db.func.now()

        try:
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al guardar en base de datos.",
                "error": str(e),
            }, 500

        return {"message": "Contraseña actualizada correctamente."}, 200
    
@api.route("/recover-password")
class RecoverPassword(Resource):
    """Permite a un admin regenerar la contraseña de un usuario."""

    @login_required
    @role_required("admin", "manager")
    def post(self):
        schema = RecoverPasswordSchema()
        try:
            payload = request.get_json() or {}
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        user = User.query.get(data["user_id"])
        if not user or user.deleted_at is not None:
            return {"message": "Usuario no encontrado."}, 404

        temp_password = generate_temp_password()
        user.password = bcrypt.generate_password_hash(temp_password).decode("utf-8")
        user.first_login = True
        user.updated_at = db.func.now()

        try:
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al guardar en base de datos.",
                "error": str(e),
            }, 500

        try:
            from app.services.email_service import send_recovered_password_email
            send_recovered_password_email(user, temp_password)
            return {
                "message": "Se generó una contraseña temporal y se envió al correo del usuario.",
            }, 200
        except Exception as e:
            return {
                "message": "Se generó la contraseña temporal, pero no se pudo enviar el correo.",
                "temporary_password": temp_password,
                "error": str(e),
            }, 200