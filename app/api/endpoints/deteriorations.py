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
    @role_required("admin", "manager")
    def get(self):
        """
        Represents a deterioration record/type in the AHML Fondos system.

        Descripción:
            Obtiene una lista paginada de tipos/registros de deterioro no eliminados lógicamente,
            permitiendo filtrar por nombre, por usuario que lo creó/modificó y hacer una búsqueda
            libre sobre nombre y descripción.

        Parámetros de consulta:
            - page (int, opcional): Número de página (por defecto 1).
            - per_page (int, opcional): Tamaño de página (por defecto 20).
            - name (str, opcional): Filtra por nombre parcial del deterioro.
            - user_id (int, opcional): Filtra por el usuario que creó/modificó el deterioro.
            - query (str, opcional): Búsqueda libre sobre name y description.

        Respuestas:
            200: Estructura con lista de deterioros y datos de paginación.
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

        query = Deterioration.query.filter(Deterioration.deleted_at.is_(None))

        # filtrar por nombre
        if name_param:
            like_name = f"%{name_param}%"
            query = query.filter(Deterioration.name.ilike(like_name))

        # filtrar por usuario
        if user_id_param:
            try:
                user_id_int = int(user_id_param)
                query = query.filter(Deterioration.user_id == user_id_int)
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

        # orden por actualización
        query = query.order_by(Deterioration.updated_at.desc())

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        items = paginated.items

        schema = DeteriorationResponseSchema(many=True)
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
    @role_required("admin", "manager")
    def post(self):
        """
        Represents a deterioration record/type in the AHML Fondos system.

        Descripción:
            Crea un nuevo tipo/registro de deterioro y lo asocia al usuario autenticado
            como creador/modificador.

        Cuerpo (JSON):
            - name (str, requerido): Nombre del deterioro (ej. "Humedad", "Rotura").
            - description (str, opcional): Descripción más detallada.

        Respuestas:
            201: Deterioro creado correctamente.
            400: Error de validación.
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
                "email": deterioration.user.email,
            }
            if deterioration.user
            else None
        )

        return {
            "message": "Deterioro creado correctamente.",
            "deterioration": resp,
        }, 201


@api.route("/<int:deterioration_id>")
class DeteriorationDetail(Resource):
    @login_required
    @role_required("admin", "manager")
    def get(self, deterioration_id: int):
        """
        Represents a deterioration record/type in the AHML Fondos system.

        Descripción:
            Obtiene un registro de deterioro por su identificador, incluyendo
            los datos del usuario que lo creó/modificó.

        Parámetros de ruta:
            - deterioration_id (int): Identificador del deterioro.

        Respuestas:
            200: Deterioro obtenido correctamente.
            404: Deterioro no encontrado o eliminado lógicamente.
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
                "email": deterioration.user.email,
            }
            if deterioration.user
            else None
        )

        return {
            "message": "Deterioro obtenido correctamente.",
            "deterioration": resp,
        }, 200

    @login_required
    @role_required("admin", "manager")
    def put(self, deterioration_id: int):
        """
        Represents a deterioration record/type in the AHML Fondos system.

        Descripción:
            Actualiza parcialmente un registro de deterioro. Permite cambiar el nombre
            y la descripción. La modificación se registra con el usuario autenticado.

        Parámetros de ruta:
            - deterioration_id (int): Identificador del deterioro a actualizar.

        Cuerpo (JSON):
            - name (str, opcional): Nuevo nombre.
            - description (str, opcional): Nueva descripción.

        Respuestas:
            200: Deterioro actualizado correctamente.
            400: Error de validación.
            404: Deterioro no encontrado.
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

        # registrar quién modificó
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
                "email": deterioration.user.email,
            }
            if deterioration.user
            else None
        )

        return {
            "message": "Deterioro actualizado correctamente.",
            "deterioration": resp,
        }, 200

    @login_required
    @role_required("admin", "manager")
    def delete(self, deterioration_id: int):
        """
        Represents a deterioration record/type in the AHML Fondos system.

        Descripción:
            Realiza un borrado lógico del registro de deterioro, registrando
            la fecha de eliminación. No elimina físicamente el registro.

        Parámetros de ruta:
            - deterioration_id (int): Identificador del deterioro a eliminar.

        Respuestas:
            200: Deterioro eliminado lógicamente.
            404: Deterioro no encontrado.
        """
        deterioration = Deterioration.query.get(deterioration_id)
        if not deterioration or deterioration.deleted_at is not None:
            return {"message": "Deterioro no encontrado."}, 404

        deterioration.deleted_at = db.func.now()
        deterioration.user_id = current_user.id if current_user.is_authenticated else deterioration.user_id

        db.session.commit()

        return {"message": "Deterioro eliminado correctamente."}, 200
