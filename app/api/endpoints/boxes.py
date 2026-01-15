"""Endpoints de gestión de cajas (Box) para AHML Fondos."""

from flask import request
from flask_login import login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy import or_, desc
from sqlalchemy.exc import SQLAlchemyError
from app.models.record_file import RecordFile
from app.extensions import db
from app.models.box import Box
from app.schemas.box import (
    BoxCreateSchema,
    BoxUpdateSchema,
    BoxResponseSchema,
)
from app.models.physical_location import PhysicalLocation
from app.utils.security import role_required

api = Namespace("boxes", description="Operaciones de gestión de cajas")


@api.route("")
class BoxList(Resource):
    @login_required
    @role_required("admin", "manager", "archivist")
    def get(self):
        """
        Obtiene una lista paginada de cajas no eliminadas lógicamente,
        permitiendo filtrar por número de caja, ubicación física, usuario,
        estado y búsqueda libre.
        """
        box_number_param = request.args.get("box_number", "").strip()
        physical_location_id_param = request.args.get("physical_location_id")
        user_id_param = request.args.get("user_id")
        is_active_param = request.args.get("is_active")
        query_param = request.args.get("query", "").strip()

        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 20))
        except ValueError:
            page = 1
            per_page = 20

        query = Box.query.filter(Box.deleted_at.is_(None))

        # Filtrar por estado
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ("true", "1", "yes")
            query = query.filter(Box.is_active.is_(is_active_bool))

        # Filtrar por número de caja
        if box_number_param:
            like_box = f"%{box_number_param}%"
            query = query.filter(Box.box_number.ilike(like_box))

        # Filtrar por ubicación física
        if physical_location_id_param:
            try:
                pid = int(physical_location_id_param)
                query = query.filter(Box.physical_location_id == pid)
            except ValueError:
                pass

        # Filtrar por usuario
        if user_id_param:
            try:
                uid = int(user_id_param)
                query = query.filter(Box.user_id == uid)
            except ValueError:
                pass

        # Búsqueda libre
        if query_param:
            like = f"%{query_param}%"
            query = (
                query
                .join(PhysicalLocation, Box.physical_location_id == PhysicalLocation.id)
                .filter(
                    or_(
                        Box.box_number.ilike(like),
                        PhysicalLocation.code.ilike(like),
                        PhysicalLocation.description.ilike(like),
                    )
                )
            )

        # Orden
        query = query.order_by(
            desc(Box.is_active),
            desc(Box.updated_at)
        )

        paginated = query.paginate(
            page=page, per_page=per_page, error_out=False)
        items = paginated.items

        schema = BoxResponseSchema(many=True)
        data = schema.dump(items)

        # Anidar usuario
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
            "message": "Cajas obtenidas correctamente.",
            "boxes": data,
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
        Crea una nueva caja.

        Cuerpo (JSON):
            - box_number (str, requerido)
            - physical_location_id (int, requerido)
            - description (str, opcional)
        """
        schema = BoxCreateSchema()
        try:
            payload = request.get_json() or {}
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400
        physical_location = PhysicalLocation.query.filter(
            PhysicalLocation.id == data["physical_location_id"],
            PhysicalLocation.deleted_at.is_(None),
        ).first()

        if not physical_location:
            return {
                "message": "Ubicación física no encontrada.",
                "field": "physical_location_id",
            }, 400

        if not physical_location.is_active:
            return {
                "message": "La ubicación física está inactiva.",
                "field": "physical_location_id",
            }, 400

        box = Box(
            box_number=data["box_number"],
            physical_location_id=data["physical_location_id"],
            description=data.get("description"),
            user_id=current_user.id if current_user.is_authenticated else None,
        )

        db.session.add(box)
        db.session.commit()

        resp_schema = BoxResponseSchema()
        resp = resp_schema.dump(box)
        resp["user"] = (
            {
                "id": box.user.id,
                "first_name": box.user.first_name,
                "last_name": box.user.last_name,
                "employee_id": box.user.employee_id,
                "email": box.user.email,
            }
            if box.user else None
        )

        return {
            "message": "Caja creada correctamente.",
            "box": resp,
        }, 201


@api.route("/<int:box_id>")
class BoxDetail(Resource):
    @login_required
    @role_required("admin", "manager", "archivist")
    def get(self, box_id: int):
        """Obtiene una caja por ID."""
        box = Box.query.get(box_id)
        if not box or box.deleted_at is not None:
            return {"message": "Caja no encontrada."}, 404

        resp_schema = BoxResponseSchema()
        resp = resp_schema.dump(box)
        resp["user"] = (
            {
                "id": box.user.id,
                "first_name": box.user.first_name,
                "last_name": box.user.last_name,
                "employee_id": box.user.employee_id,
                "email": box.user.email,
            }
            if box.user else None
        )

        return {
            "message": "Caja obtenida correctamente.",
            "box": resp,
        }, 200

    @login_required
    @role_required("admin", "manager", "archivist")
    def put(self, box_id: int):
        """
        Actualiza parcialmente una caja.
        Permite modificar: box_number, physical_location_id, description, is_active.
        """
        schema = BoxUpdateSchema()
        try:
            payload = request.get_json() or {}
            payload["id"] = box_id
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        box = Box.query.get(box_id)
        if not box or box.deleted_at is not None:
            return {"message": "Caja no encontrada."}, 404

        # 🔴 VALIDAR physical_location_id SI VIENE
        if "physical_location_id" in data:
            physical_location = PhysicalLocation.query.filter(
                PhysicalLocation.id == data["physical_location_id"],
                PhysicalLocation.deleted_at.is_(None),
            ).first()

            if not physical_location:
                return {
                    "message": "Ubicación física no encontrada.",
                    "field": "physical_location_id",
                }, 400

            if not physical_location.is_active:
                return {
                    "message": "La ubicación física está inactiva.",
                    "field": "physical_location_id",
                }, 400

            box.physical_location_id = data["physical_location_id"]

        # Actualizaciones normales
        if "box_number" in data:
            box.box_number = data["box_number"]

        if "description" in data:
            box.description = data["description"]

        if "is_active" in data:
            box.is_active = data["is_active"]

        box.user_id = current_user.id if current_user.is_authenticated else box.user_id

        try:
            box.updated_at = db.func.now()
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al guardar en base de datos.",
                "error": str(e),
            }, 500

        resp_schema = BoxResponseSchema()
        resp = resp_schema.dump(box)
        resp["user"] = (
            {
                "id": box.user.id,
                "first_name": box.user.first_name,
                "last_name": box.user.last_name,
                "employee_id": box.user.employee_id,
                "email": box.user.email,
            }
            if box.user else None
        )

        return {
            "message": "Caja actualizada correctamente.",
            "box": resp,
        }, 200

    @login_required
    @role_required("admin", "manager", "archivist")
    def delete(self, box_id: int):
        """
        Borrado lógico de una caja:
        - NO se permite si tiene expedientes asociados
        """
        box = Box.query.get(box_id)
        if not box or box.deleted_at is not None:
            return {"message": "Caja no encontrada."}, 404

        # 🔴 VALIDAR SI TIENE EXPEDIENTES
        has_record_files = (
            db.session.query(RecordFile.id)
            .filter(
                RecordFile.box_id == box.id,
                RecordFile.deleted_at.is_(None),
            )
            .first()
            is not None
        )

        if has_record_files:
            return {
                "message": "La caja contiene expedientes asociados y no puede eliminarse.",
            }, 400

        box.deleted_at = db.func.now()
        box.is_active = False
        box.user_id = current_user.id if current_user.is_authenticated else box.user_id

        db.session.commit()

        return {"message": "Caja eliminada correctamente."}, 200