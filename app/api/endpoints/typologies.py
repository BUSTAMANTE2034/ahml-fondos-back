"""Endpoints de gestión de tipologías documentales (JSON)."""

from flask import request
from flask_login import login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.typology import Typology
from app.schemas.typology import (
    TypologyCreateSchema,
    TypologyUpdateSchema,
    TypologyResponseSchema,
)
from app.utils.security import role_required

api = Namespace("typologies", description="Operaciones de gestión de tipologías documentales")


@api.route("")
class TypologyList(Resource):
    @login_required
    @role_required("admin", "manager")
    def get(self):
        """
        Represents a documentary typology in the AHML Fondos system.

        Descripción:
            Obtiene una lista paginada de tipologías documentales no eliminadas lógicamente,
            permitiendo filtrar por nombre, por usuario que la creó/modificó y hacer una
            búsqueda libre sobre nombre y descripción.

        Parámetros de consulta:
            - page (int, opcional): Número de página (por defecto 1).
            - per_page (int, opcional): Tamaño de página (por defecto 20).
            - name (str, opcional): Filtra por nombre parcial de la tipología.
            - user_id (int, opcional): Filtra por el usuario que creó/modificó la tipología.
            - query (str, opcional): Búsqueda libre sobre name y description.

        Respuestas:
            200: Estructura con lista de tipologías y datos de paginación.
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

        query = Typology.query.filter(Typology.deleted_at.is_(None))

        # filtrar por nombre
        if name_param:
            like_name = f"%{name_param}%"
            query = query.filter(Typology.name.ilike(like_name))

        # filtrar por usuario
        if user_id_param:
            try:
                user_id_int = int(user_id_param)
                query = query.filter(Typology.user_id == user_id_int)
            except ValueError:
                pass

        # búsqueda libre
        if query_param:
            like = f"%{query_param}%"
            query = query.filter(
                or_(
                    Typology.name.ilike(like),
                    Typology.description.ilike(like),
                )
            )

        # orden por actualización
        query = query.order_by(Typology.updated_at.desc())

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        items = paginated.items

        schema = TypologyResponseSchema(many=True)
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
            "message": "Tipologías obtenidas correctamente.",
            "typologies": data,
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
        Represents a documentary typology in the AHML Fondos system.

        Descripción:
            Crea una nueva tipología documental y la asocia al usuario autenticado
            como creador/modificador.

        Cuerpo (JSON):
            - name (str, requerido): Nombre de la tipología.
            - description (str, opcional): Descripción detallada.

        Respuestas:
            201: Tipología creada correctamente.
            400: Error de validación.
        """
        schema = TypologyCreateSchema()
        try:
            payload = request.get_json() or {}
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        typology = Typology(
            name=data["name"],
            description=data.get("description"),
            user_id=current_user.id if current_user.is_authenticated else None,
        )

        db.session.add(typology)
        db.session.commit()

        resp_schema = TypologyResponseSchema()
        resp = resp_schema.dump(typology)
        resp["user"] = (
            {
                "id": typology.user.id,
                "first_name": typology.user.first_name,
                "last_name": typology.user.last_name,
                "email": typology.user.email,
            }
            if typology.user
            else None
        )

        return {
            "message": "Tipología creada correctamente.",
            "typology": resp,
        }, 201


@api.route("/<int:typology_id>")
class TypologyDetail(Resource):
    @login_required
    @role_required("admin", "manager")
    def get(self, typology_id: int):
        """
        Represents a documentary typology in the AHML Fondos system.

        Descripción:
            Obtiene una tipología documental por su identificador, incluyendo los datos
            del usuario que la creó/modificó.

        Parámetros de ruta:
            - typology_id (int): Identificador de la tipología.

        Respuestas:
            200: Tipología obtenida correctamente.
            404: Tipología no encontrada o eliminada lógicamente.
        """
        typology = Typology.query.get(typology_id)
        if not typology or typology.deleted_at is not None:
            return {"message": "Tipología no encontrada."}, 404

        resp_schema = TypologyResponseSchema()
        resp = resp_schema.dump(typology)
        resp["user"] = (
            {
                "id": typology.user.id,
                "first_name": typology.user.first_name,
                "last_name": typology.user.last_name,
                "email": typology.user.email,
            }
            if typology.user
            else None
        )

        return {
            "message": "Tipología obtenida correctamente.",
            "typology": resp,
        }, 200

    @login_required
    @role_required("admin", "manager")
    def put(self, typology_id: int):
        """
        Represents a documentary typology in the AHML Fondos system.

        Descripción:
            Actualiza parcialmente una tipología documental existente. Permite modificar
            el nombre y la descripción. La modificación se registra con el usuario autenticado.

        Parámetros de ruta:
            - typology_id (int): Identificador de la tipología a actualizar.

        Cuerpo (JSON):
            - name (str, opcional): Nuevo nombre de la tipología.
            - description (str, opcional): Nueva descripción.

        Respuestas:
            200: Tipología actualizada correctamente.
            400: Error de validación.
            404: Tipología no encontrada.
        """
        schema = TypologyUpdateSchema()
        try:
            payload = request.get_json() or {}
            payload["id"] = typology_id
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        typology = Typology.query.get(typology_id)
        if not typology or typology.deleted_at is not None:
            return {"message": "Tipología no encontrada."}, 404

        if "name" in data:
            typology.name = data["name"]
        if "description" in data:
            typology.description = data["description"]

        # registrar quién modificó
        typology.user_id = current_user.id if current_user.is_authenticated else typology.user_id

        try:
            typology.updated_at = db.func.now()
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al guardar en base de datos.",
                "error": str(e),
            }, 500

        resp_schema = TypologyResponseSchema()
        resp = resp_schema.dump(typology)
        resp["user"] = (
            {
                "id": typology.user.id,
                "first_name": typology.user.first_name,
                "last_name": typology.user.last_name,
                "email": typology.user.email,
            }
            if typology.user
            else None
        )

        return {
            "message": "Tipología actualizada correctamente.",
            "typology": resp,
        }, 200

    @login_required
    @role_required("admin", "manager")
    def delete(self, typology_id: int):
        """
        Represents a documentary typology in the AHML Fondos system.

        Descripción:
            Realiza un borrado lógico de la tipología documental, registrando la fecha
            de eliminación. No elimina físicamente el registro.

        Parámetros de ruta:
            - typology_id (int): Identificador de la tipología a eliminar.

        Respuestas:
            200: Tipología eliminada lógicamente.
            404: Tipología no encontrada.
        """
        typology = Typology.query.get(typology_id)
        if not typology or typology.deleted_at is not None:
            return {"message": "Tipología no encontrada."}, 404

        typology.deleted_at = db.func.now()
        typology.user_id = current_user.id if current_user.is_authenticated else typology.user_id

        db.session.commit()

        return {"message": "Tipología eliminada correctamente."}, 200
