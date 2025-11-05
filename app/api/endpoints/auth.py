"""Endpoints de autenticación.

Define endpoints para autenticación de usuarios y manejo de sesión.
Implementa validación con schemas para requests y responses.
"""

from datetime import datetime, timezone
from flask import request
from flask_login import login_user, logout_user, login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError

from app.extensions import bcrypt, db
from app.models.user import User
from app.schemas.auth import (
    LoginSchema,
    LoginResponseSchema,
    LogoutSchema,
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
            # Actualiza último acceso
            user.last_login = datetime.now(timezone.utc)
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
