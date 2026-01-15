"""Endpoints de gestión de ubicaciones físicas (PhysicalLocation) para AHML Fondos."""

from flask import request
from flask_login import login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy import or_, desc
from sqlalchemy.exc import SQLAlchemyError
from app.models.box import Box
from app.extensions import db
from app.models.physical_location import PhysicalLocation
from app.schemas.physical_location import (
    PhysicalLocationBaseSchema,
    PhysicalLocationCreateSchema,
    PhysicalLocationUpdateSchema,
)
from app.utils.security import role_required

api = Namespace("physical_locations", description="Gestión de ubicaciones físicas generales")


@api.route("")
class PhysicalLocationList(Resource):
    @login_required
    @role_required("admin", "manager", "archivist")
    def get(self):
        """
        Obtiene una lista paginada de ubicaciones físicas no eliminadas,
        permite filtrar por código, descripción, estado y búsqueda libre.
        """
        code_param = request.args.get("code", "").strip()
        is_active_param = request.args.get("is_active")
        query_param = request.args.get("query", "").strip()

        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 20))
        except ValueError:
            page = 1
            per_page = 20

        query = PhysicalLocation.query.filter(PhysicalLocation.deleted_at.is_(None))

        # Filtrar por estado
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ("true", "1", "yes")
            query = query.filter(PhysicalLocation.is_active.is_(is_active_bool))

        # Filtrar por código
        if code_param:
            like_code = f"%{code_param}%"
            query = query.filter(PhysicalLocation.code.ilike(like_code))

        # Búsqueda libre
        if query_param:
            like = f"%{query_param}%"
            query = query.filter(
                or_(
                    PhysicalLocation.code.ilike(like),
                    PhysicalLocation.description.ilike(like),
                )
            )

        # Orden
        query = query.order_by(
            desc(PhysicalLocation.is_active),
            desc(PhysicalLocation.updated_at)
        )

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        items = paginated.items

        schema = PhysicalLocationBaseSchema(many=True)
        data = schema.dump(items)
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
            "message": "Ubicaciones físicas obtenidas correctamente.",
            "physical_locations": data,
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
    @role_required("admin", "manager", "archivist")
    def post(self):
        """
        Crea una nueva ubicación física.

        Cuerpo (JSON):
            - code (str, requerido)
            - description (str, opcional)
        """
        schema = PhysicalLocationCreateSchema()
        try:
            payload = request.get_json() or {}
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        physical_location = PhysicalLocation(
            code=data["code"],
            description=data.get("description"),
            user_id=current_user.id if current_user.is_authenticated else None,
        )

        db.session.add(physical_location)
        db.session.commit()

        resp_schema = PhysicalLocationBaseSchema()
        resp = resp_schema.dump(physical_location)

        return {
            "message": "Ubicación física creada correctamente.",
            "physical_location": resp,
        }, 201


@api.route("/<int:physical_location_id>")
class PhysicalLocationDetail(Resource):
    @login_required
    @role_required("admin", "manager", "archivist")
    def get(self, physical_location_id: int):
        """Obtiene una ubicación física por ID."""
        pl = PhysicalLocation.query.get(physical_location_id)
        if not pl or pl.deleted_at is not None:
            return {"message": "Ubicación física no encontrada."}, 404

        resp_schema = PhysicalLocationBaseSchema()
        resp = resp_schema.dump(pl)

        return {
            "message": "Ubicación física obtenida correctamente.",
            "physical_location": resp,
        }, 200

    @login_required
    @role_required("admin", "manager", "archivist")
    def put(self, physical_location_id: int):
        """
        Actualiza parcialmente una ubicación física.
        Permite modificar: code, description.
        """
        schema = PhysicalLocationUpdateSchema()
        try:
            payload = request.get_json() or {}
            payload["id"] = physical_location_id
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        pl = PhysicalLocation.query.get(physical_location_id)
        if not pl or pl.deleted_at is not None:
            return {"message": "Ubicación física no encontrada."}, 404

        if "code" in data:
            pl.code = data["code"]
        if "description" in data:
            pl.description = data["description"]
        if "is_active" in data:
            pl.is_active = data["is_active"]

        pl.user_id = current_user.id if current_user.is_authenticated else pl.user_id

        try:
            pl.updated_at = db.func.now()
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al guardar en base de datos.",
                "error": str(e),
            }, 500

        resp_schema = PhysicalLocationBaseSchema()
        resp = resp_schema.dump(pl)

        return {
            "message": "Ubicación física actualizada correctamente.",
            "physical_location": resp,
        }, 200

    @login_required
    @role_required("admin", "manager", "archivist")
    def delete(self, physical_location_id: int):
        """
        Borrado lógico de una ubicación física:
        - NO se permite si tiene cajas asociadas
        """
        pl = PhysicalLocation.query.get(physical_location_id)
        if not pl or pl.deleted_at is not None:
            return {"message": "Ubicación física no encontrada."}, 404

        # 🔴 VALIDAR CAJAS ASOCIADAS
        has_boxes = (
            db.session.query(Box.id)
            .filter(
                Box.physical_location_id == pl.id,
                Box.deleted_at.is_(None),
            )
            .first()
            is not None
        )

        if has_boxes:
            return {
                "message": "La ubicación física tiene cajas asociadas y no puede eliminarse.",
            }, 400

        pl.deleted_at = db.func.now()
        pl.is_active = False
        pl.user_id = current_user.id if current_user.is_authenticated else pl.user_id

        db.session.commit()

        return {"message": "Ubicación física eliminada correctamente."}, 200