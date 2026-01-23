"""Endpoints de gestión de deterioros documentales (JSON)."""

from flask import request
from flask_login import login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.deterioration import Deterioration
from app.schemas.deterioration import (
    DeteriorationCreateSchema,
    DeteriorationUpdateSchema,
    DeteriorationResponseSchema,
)
from app.utils.security import role_required

api = Namespace("deteriorations", description="Operaciones de gestión de deterioros documentales")


@api.route("")
class DeteriorationList(Resource):
    @login_required
    @role_required("admin", "manager","archivist")
    def get(self):
        """
        Obtiene lista paginada de deterioros no eliminados lógicamente,
        con filtros por nombre, usuario, estado y búsqueda libre.
        """
        name_param = request.args.get("name", "").strip()
        user_id_param = request.args.get("user_id")
        is_active_param = request.args.get("is_active")
        query_param = request.args.get("query", "").strip()
        

        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 20))
        except ValueError:
            page = 1
            per_page = 20

        query = Deterioration.query.filter(Deterioration.deleted_at.is_(None))

        # estado
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ("true", "1", "yes")
            query = query.filter(Deterioration.is_active.is_(is_active_bool))

        # por nombre
        if name_param:
            like_name = f"%{name_param}%"
            query = query.filter(Deterioration.name.ilike(like_name))

        # por usuario
        if user_id_param:
            try:
                uid = int(user_id_param)
                query = query.filter(Deterioration.user_id == uid)
            except ValueError:
                pass

        # búsqueda libre
        if query_param:
            like = f"%{query_param}%"
            query = query.filter(
                or_(
                    Deterioration.name.ilike(like),
                    Deterioration.description.ilike(like),
                )
            )

        # orden uniformado: activos primero, luego updated_at DESC
        from sqlalchemy import desc
        query = query.order_by(
            desc(Deterioration.is_active),
            desc(Deterioration.updated_at)
        )

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        items = paginated.items

        schema = DeteriorationResponseSchema(many=True)
        data = schema.dump(items)

        # anidar user con employee_id
        for i, item in enumerate(items):
            data[i]["user"] = (
                {
                    "id": item.user.id,
                    "first_name": item.user.first_name,
                    "last_name": item.user.last_name,
                    "employee_id": item.user.employee_id,
                    "email": item.user.email,
                }
                if item.user else None
            )

        return {
            "message": "Deterioros obtenidos correctamente.",
            "deteriorations": data,
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
    @role_required("admin", "manager","archivist")
    def post(self):
        """
        Crea un nuevo deterioro.
        """
        schema = DeteriorationCreateSchema()
        try:
            payload = request.get_json() or {}
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        deterioration = Deterioration(
            name=data["name"],
            description=data.get("description"),
            is_active=data.get("is_active", True),
            user_id=current_user.id if current_user.is_authenticated else None,
        )

        db.session.add(deterioration)
        db.session.commit()

        resp_schema = DeteriorationResponseSchema()
        resp = resp_schema.dump(deterioration)
        resp["user"] = (
            {
                "id": deterioration.user.id,
                "first_name": deterioration.user.first_name,
                "last_name": deterioration.user.last_name,
                "employee_id": deterioration.user.employee_id,
                "email": deterioration.user.email,
            }
            if deterioration.user else None
        )

        return {
            "message": "Deterioro creado correctamente.",
            "deterioration": resp,
        }, 201


@api.route("/<int:deterioration_id>")
class DeteriorationDetail(Resource):

    @login_required
    @role_required("admin", "manager","archivist")
    def get(self, deterioration_id: int):
        """
        Obtiene deterioro por ID.
        """
        deterioration = Deterioration.query.get(deterioration_id)
        if not deterioration or deterioration.deleted_at is not None:
            return {"message": "Deterioro no encontrado."}, 404

        resp_schema = DeteriorationResponseSchema()
        resp = resp_schema.dump(deterioration)
        resp["user"] = (
            {
                "id": deterioration.user.id,
                "first_name": deterioration.user.first_name,
                "last_name": deterioration.user.last_name,
                "employee_id": deterioration.user.employee_id,
                "email": deterioration.user.email,
            }
            if deterioration.user else None
        )

        return {
            "message": "Deterioro obtenido correctamente.",
            "deterioration": resp,
        }, 200

    @login_required
    @role_required("admin", "manager","archivist")
    def put(self, deterioration_id: int):
        """
        Actualiza parcialmente un deterioro.
        Permite modificar: name, description, is_active.
        """
        schema = DeteriorationUpdateSchema()
        try:
            payload = request.get_json() or {}
            payload["id"] = deterioration_id
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        deterioration = Deterioration.query.get(deterioration_id)
        if not deterioration or deterioration.deleted_at is not None:
            return {"message": "Deterioro no encontrado."}, 404

        if "name" in data:
            deterioration.name = data["name"]
        if "description" in data:
            deterioration.description = data["description"]
        if "is_active" in data:
            deterioration.is_active = data["is_active"]

        deterioration.user_id = current_user.id if current_user.is_authenticated else deterioration.user_id

        try:
            deterioration.updated_at = db.func.now()
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al guardar en base de datos.",
                "error": str(e),
            }, 500

        resp_schema = DeteriorationResponseSchema()
        resp = resp_schema.dump(deterioration)
        resp["user"] = (
            {
                "id": deterioration.user.id,
                "first_name": deterioration.user.first_name,
                "last_name": deterioration.user.last_name,
                "employee_id": deterioration.user.employee_id,
                "email": deterioration.user.email,
            }
            if deterioration.user else None
        )

        return {
            "message": "Deterioro actualizado correctamente.",
            "deterioration": resp,
        }, 200

    @login_required
    @role_required("admin", "manager","archivist")
    def delete(self, deterioration_id: int):
        """
        Borrado lógico:
            - deleted_at = NOW()
            - is_active = False
        """
        deterioration = Deterioration.query.get(deterioration_id)
        if not deterioration or deterioration.deleted_at is not None:
            return {"message": "Deterioro no encontrado."}, 404

        deterioration.deleted_at = db.func.now()
        deterioration.is_active = False
        deterioration.user_id = current_user.id if current_user.is_authenticated else deterioration.user_id

        db.session.commit()

        return {"message": "Deterioro eliminado correctamente."}, 200
