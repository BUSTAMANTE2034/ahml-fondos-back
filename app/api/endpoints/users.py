"""Endpoints de gestión de usuarios (JSON)."""

from flask import request
from flask_login import login_required
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy import or_, case
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from flask_login import current_user
from app.extensions import db, bcrypt
from app.models.user import User
from app.schemas.user import (
    UserCreateSchema,
    UserUpdateSchema,
    UserResponseSchema,
)
from app.utils.security import role_required, generate_temp_password
from app.services.email_service import (
    send_temp_password_email,
    send_password_updated_email,
)

api = Namespace("users", description="Operaciones de gestión de usuarios")

@api.route("")
class UsersList(Resource):
    """Listado y creación de usuarios."""
    @login_required
    @role_required("admin", "manager")
    def get(self):
        print("USER:", current_user, current_user.is_authenticated, getattr(current_user, "role", None))
        """Obtener usuarios con filtros y paginación (JSON)."""
        is_active_param = request.args.get("is_active")
        role_param = request.args.get("role")
        query_param = request.args.get("query", "").strip()

        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 20))
        except ValueError:
            page = 1
            per_page = 20

        query = User.query.filter(User.deleted_at.is_(None))

        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ("true", "1", "yes")
            query = query.filter(User.is_active.is_(is_active_bool))

        if role_param and role_param != "all":
            query = query.filter(User.role == role_param)

        if query_param:
            like_pattern = f"%{query_param}%"
            if query_param.isdigit():
                query = query.filter(
                    or_(
                        User.id == int(query_param),
                        User.employee_id.ilike(like_pattern),
                        User.first_name.ilike(like_pattern),
                        User.last_name.ilike(like_pattern),
                        User.email.ilike(like_pattern),
                    )
                )
            else:
                query = query.filter(
                    or_(
                        User.employee_id.ilike(like_pattern),
                        User.first_name.ilike(like_pattern),
                        User.last_name.ilike(like_pattern),
                        User.email.ilike(like_pattern),
                    )
                )

        query = query.order_by(
    User.is_active.desc(),     # Primero activos (True=1) luego inactivos (False=0)
    User.updated_at.desc()     # Más recientes primero
)

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        users = paginated.items

        return {
            "message": "Usuarios obtenidos correctamente.",
            "users": UserResponseSchema(many=True).dump(users),
            "pagination": {
                "total": paginated.total,
                "pages": paginated.pages,
                "current_page": paginated.page,
                "per_page": paginated.per_page,
                "has_next": paginated.has_next,
                "has_prev": paginated.has_prev,
                "next_page": paginated.next_num if paginated.has_next else None,
                "prev_page": paginated.prev_num if paginated.has_prev else None,
            },
        }, 200

    @login_required
    @role_required("admin", "manager")
    def post(self):
        """Crear un nuevo usuario (JSON) con contraseña temporal."""
        schema = UserCreateSchema()
        try:
            payload = request.get_json() or {}
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        # validaciones "a mano"
        existing_email = (
            User.query.filter(User.email == data["email"], User.deleted_at.is_(None))
            .first()
        )
        if existing_email:
            return {"message": "El correo ya está registrado."}, 400

        existing_emp = (
            User.query.filter(
                User.employee_id == data["employee_id"],
                User.deleted_at.is_(None),
            )
            .first()
        )
        if existing_emp:
            return {"message": "El número de empleado ya está registrado."}, 400

        temp_password = generate_temp_password()

        user = User(
            employee_id=data["employee_id"],
            first_name=data["first_name"],
            last_name=data.get("last_name"),
            email=data["email"],
            password=bcrypt.generate_password_hash(temp_password).decode("utf-8"),
            role=data.get("role", "visitor"),
            is_active=True,
            first_login=True,
        )

        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            err_str = str(e.orig)
            if "employee_id" in err_str:
                return {"message": "El número de empleado ya está registrado."}, 400
            if "email" in err_str:
                return {"message": "El correo ya está registrado."}, 400
            return {"message": "No se pudo crear el usuario (dato duplicado)."}, 400

        try:
            send_temp_password_email(user, temp_password)
            msg = "Usuario creado correctamente. Se envió la contraseña temporal al correo."
            return {
                "message": msg,
                "user": UserResponseSchema().dump(user),
            }, 201
        except Exception as e:
            return {
                "message": "Usuario creado, pero no se pudo enviar el correo.",
                "temporary_password": temp_password,
                "user": UserResponseSchema().dump(user),
                "error": str(e),
            }, 201


@api.route("/<int:user_id>")
class UserDetail(Resource):
    """Operaciones sobre un usuario específico."""

    @login_required
    @role_required("admin", "manager")
    def get(self, user_id: int):
        """Obtener un usuario por ID (solo no borrados)."""
        user = User.query.get(user_id)
        if not user or user.deleted_at is not None:
            return {"message": "Usuario no encontrado."}, 404

        return {
            "message": "Usuario obtenido correctamente.",
            "user": UserResponseSchema().dump(user),
        }, 200

    @login_required
    @role_required("admin", "manager")
    def put(self, user_id: int):
        """Actualizar un usuario (JSON)."""
        schema = UserUpdateSchema()
        try:
            payload = request.get_json() or {}
            payload["id"] = user_id
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        user = User.query.get(user_id)
        if not user or user.deleted_at is not None:
            return {"message": "Usuario no encontrado."}, 404

        # actualizaciones de campos "normales"
        if "first_name" in data:
            user.first_name = data["first_name"]
        if "last_name" in data:
            user.last_name = data["last_name"]
        if "role" in data:
            user.role = data["role"]
        if "is_active" in data:
            user.is_active = data["is_active"]

        plain_password = data.get("password")
        if plain_password:
            user.password = bcrypt.generate_password_hash(plain_password).decode("utf-8")
            user.first_login = True

        # estos dos son los que pueden chocar en BD
        if "employee_id" in data:
            user.employee_id = data["employee_id"]
        if "email" in data:
            user.email = data["email"]

        try:
            user.updated_at = db.func.now()
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            err_str = str(e.orig)
            # aquí devolvemos 409 porque es conflicto de recurso existente
            if "employee_id" in err_str:
                return {
                    "message": "El número de empleado ya está en uso por otro usuario."
                }, 409
            if "email" in err_str:
                return {
                    "message": "El correo ya está en uso por otro usuario."
                }, 409
            return {
                "message": "Error de integridad al actualizar el usuario.",
                "error": err_str,
            }, 400
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al guardar en base de datos.",
                "error": str(e),
            }, 500

        # si se cambió password, intentamos mandar correo
        if plain_password:
            try:
                send_password_updated_email(user, plain_password)
            except Exception:
                # no rompemos la respuesta por el correo
                pass

        return {
            "message": "Usuario actualizado correctamente.",
            "user": UserResponseSchema().dump(user),
        }, 200

    @login_required
    @role_required("admin", "manager")
    def delete(self, user_id: int):
        """Eliminar (lógicamente) un usuario."""
        user = User.query.get(user_id)
        if not user or user.deleted_at is not None:
            return {"message": "Usuario no encontrado."}, 404

        user.deleted_at = db.func.now()
        user.is_active = False
        db.session.commit()

        return {"message": "Usuario eliminado correctamente."}, 200
