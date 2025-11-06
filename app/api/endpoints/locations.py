"""Endpoints de gestión de ubicaciones físicas (JSON)."""

from flask import request
from flask_login import login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.location import Location
from app.schemas.location import (
    LocationCreateSchema,
    LocationUpdateSchema,
    LocationResponseSchema,
)
from app.utils.security import role_required

api = Namespace("locations", description="Operaciones de gestión de ubicaciones físicas")


@api.route("")
class LocationList(Resource):
    @login_required
    @role_required("admin", "manager")
    def get(self):
        """
        Represents a physical/archive location in the AHML Fondos system.

        Descripción:
            Obtiene una lista paginada de ubicaciones no eliminadas lógicamente,
            permitiendo filtrar por nombre, por usuario que la creó/modificó
            y realizar una búsqueda libre.

        Parámetros de consulta:
            - page (int, opcional): Número de página (por defecto 1).
            - per_page (int, opcional): Tamaño de página (por defecto 20).
            - name (str, opcional): Filtra por nombre parcial de la ubicación.
            - user_id (int, opcional): Filtra por el usuario que creó/modificó la ubicación.
            - query (str, opcional): Búsqueda libre aplicada sobre name.

        Respuestas:
            200: Estructura con lista de ubicaciones y datos de paginación.
        """
        name_param = request.args.get("name", "").strip()
        user_id_param = request.args.get("user_id")
        query_param = request.args.get("query", "").strip()

        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 20))
        except ValueError:
            page = 1
            per_page = 20

        query = Location.query.filter(Location.deleted_at.is_(None))

        # filtrar por nombre
        if name_param:
            like_name = f"%{name_param}%"
            query = query.filter(Location.name.ilike(like_name))

        # filtrar por usuario
        if user_id_param:
            try:
                user_id_int = int(user_id_param)
                query = query.filter(Location.user_id == user_id_int)
            except ValueError:
                pass

        # búsqueda libre
        if query_param:
            like = f"%{query_param}%"
            query = query.filter(
                or_(
                    Location.name.ilike(like),
                )
            )

        # orden por actualización más reciente
        query = query.order_by(Location.updated_at.desc())

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        items = paginated.items

        schema = LocationResponseSchema(many=True)
        data = schema.dump(items)

        # anidar user
        for i, item in enumerate(items):
            data[i]["user"] = (
                {
                    "id": item.user.id,
                    "first_name": item.user.first_name,
                    "last_name": item.user.last_name,
                    "email": item.user.email,
                }
                if item.user
                else None
            )

        return {
            "message": "Ubicaciones obtenidas correctamente.",
            "locations": data,
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
        """
        Represents a physical/archive location in the AHML Fondos system.

        Descripción:
            Crea una nueva ubicación física y la asocia al usuario autenticado
            como creador/modificador.

        Cuerpo (JSON):
            - name (str, requerido): Nombre de la ubicación (área, edificio, sala, etc.).

        Respuestas:
            201: Ubicación creada correctamente.
            400: Error de validación.
        """
        schema = LocationCreateSchema()
        try:
            payload = request.get_json() or {}
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        location = Location(
            name=data["name"],
            user_id=current_user.id if current_user.is_authenticated else None,
        )

        db.session.add(location)
        db.session.commit()

        resp_schema = LocationResponseSchema()
        resp = resp_schema.dump(location)
        resp["user"] = (
            {
                "id": location.user.id,
                "first_name": location.user.first_name,
                "last_name": location.user.last_name,
                "email": location.user.email,
            }
            if location.user
            else None
        )

        return {
            "message": "Ubicación creada correctamente.",
            "location": resp,
        }, 201


@api.route("/<int:location_id>")
class LocationDetail(Resource):
    @login_required
    @role_required("admin", "manager")
    def get(self, location_id: int):
        """
        Represents a physical/archive location in the AHML Fondos system.

        Descripción:
            Obtiene una ubicación física por su identificador, incluyendo
            los datos del usuario que la creó/modificó.

        Parámetros de ruta:
            - location_id (int): Identificador de la ubicación.

        Respuestas:
            200: Ubicación obtenida correctamente.
            404: Ubicación no encontrada o eliminada lógicamente.
        """
        location = Location.query.get(location_id)
        if not location or location.deleted_at is not None:
            return {"message": "Ubicación no encontrada."}, 404

        resp_schema = LocationResponseSchema()
        resp = resp_schema.dump(location)
        resp["user"] = (
            {
                "id": location.user.id,
                "first_name": location.user.first_name,
                "last_name": location.user.last_name,
                "email": location.user.email,
            }
            if location.user
            else None
        )

        return {
            "message": "Ubicación obtenida correctamente.",
            "location": resp,
        }, 200

    @login_required
    @role_required("admin", "manager")
    def put(self, location_id: int):
        """
        Represents a physical/archive location in the AHML Fondos system.

        Descripción:
            Actualiza parcialmente una ubicación existente. Permite modificar
            el nombre. La modificación se registra con el usuario autenticado.

        Parámetros de ruta:
            - location_id (int): Identificador de la ubicación a actualizar.

        Cuerpo (JSON):
            - name (str, opcional): Nuevo nombre de la ubicación.

        Respuestas:
            200: Ubicación actualizada correctamente.
            400: Error de validación.
            404: Ubicación no encontrada.
        """
        schema = LocationUpdateSchema()
        try:
            payload = request.get_json() or {}
            payload["id"] = location_id
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        location = Location.query.get(location_id)
        if not location or location.deleted_at is not None:
            return {"message": "Ubicación no encontrada."}, 404

        if "name" in data:
            location.name = data["name"]

        # registrar quién modificó
        location.user_id = current_user.id if current_user.is_authenticated else location.user_id

        try:
            location.updated_at = db.func.now()
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al guardar en base de datos.",
                "error": str(e),
            }, 500

        resp_schema = LocationResponseSchema()
        resp = resp_schema.dump(location)
        resp["user"] = (
            {
                "id": location.user.id,
                "first_name": location.user.first_name,
                "last_name": location.user.last_name,
                "email": location.user.email,
            }
            if location.user
            else None
        )

        return {
            "message": "Ubicación actualizada correctamente.",
            "location": resp,
        }, 200

    @login_required
    @role_required("admin", "manager")
    def delete(self, location_id: int):
        """
        Represents a physical/archive location in the AHML Fondos system.

        Descripción:
            Realiza un borrado lógico de la ubicación, marcándola con fecha de
            eliminación. No elimina físicamente el registro.

        Parámetros de ruta:
            - location_id (int): Identificador de la ubicación a eliminar.

        Respuestas:
            200: Ubicación eliminada lógicamente.
            404: Ubicación no encontrada.
        """
        location = Location.query.get(location_id)
        if not location or location.deleted_at is not None:
            return {"message": "Ubicación no encontrada."}, 404

        location.deleted_at = db.func.now()
        location.user_id = current_user.id if current_user.is_authenticated else location.user_id

        db.session.commit()

        return {"message": "Ubicación eliminada correctamente."}, 200
