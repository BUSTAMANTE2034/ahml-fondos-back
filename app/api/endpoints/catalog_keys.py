"""Endpoints de gestión de claves de catálogo (JSON)."""

from flask import request
from flask_login import login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.catalog_key import CatalogKey
from app.schemas.catalog_key import (
    CatalogKeyCreateSchema,
    CatalogKeyUpdateSchema,
    CatalogKeyResponseSchema,
)
from app.utils.security import role_required

api = Namespace("catalog-keys", description="Operaciones de gestión de claves de catálogo")


@api.route("")
class CatalogKeyList(Resource):
    @login_required
    @role_required("admin", "manager","archivist")
    def get(self):
        """
        Represents a catalog key that can be assigned to archival entities.

        Descripción:
            Obtiene una lista paginada de claves de catálogo no eliminadas lógicamente,
            permitiendo filtrar por estatus, tipo de entidad, usuario creador/modificador
            y una búsqueda libre.

        Parámetros de consulta:
            - page (int, opcional): Número de página, por defecto 1.
            - per_page (int, opcional): Tamaño de página, por defecto 20.
            - is_active (bool|str, opcional): Filtra por estado activo/inactivo ("true"/"false").
            - entity_type (str, opcional): Filtra por tipo de entidad ("fund", "section", "series", etc.).
            - user_id (int, opcional): Filtra por el usuario que creó/modificó la clave.
            - query (str, opcional): Cadena de búsqueda que aplica sobre key, name y description.

        Respuestas:
            200: Lista paginada de claves de catálogo.
            400: Parámetros de paginación inválidos.
        """
        is_active_param = request.args.get("is_active")
        entity_type_param = request.args.get("entity_type")
        user_id_param = request.args.get("user_id")
        query_param = request.args.get("query", "").strip()
        
        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 20))
        except ValueError:
            page = 1
            per_page = 20

        query = CatalogKey.query.filter(CatalogKey.deleted_at.is_(None))

        # filtro por estado
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ("true", "1", "yes")
            query = query.filter(CatalogKey.is_active.is_(is_active_bool))

        # filtro por tipo de entidad
        # if entity_type_param:
        #     query = query.filter(CatalogKey.entity_type == entity_type_param)
        if entity_type_param:
            entity_types = [e.strip() for e in entity_type_param.split(",") if e.strip()]

            if len(entity_types) == 1:
                query = query.filter(CatalogKey.entity_type == entity_types[0])
            else:
                query = query.filter(CatalogKey.entity_type.in_(entity_types))
        # NUEVO: filtro por usuario creador/modificador
        if user_id_param:
            try:
                user_id_int = int(user_id_param)
                query = query.filter(CatalogKey.user_id == user_id_int)
            except ValueError:
                # si mandan algo que no es int, simplemente no filtramos por user_id
                pass

        # búsqueda libre
        if query_param:
            like = f"%{query_param}%"
            query = query.filter(
                or_(
                    CatalogKey.key.ilike(like),
                    CatalogKey.name.ilike(like),
                    CatalogKey.description.ilike(like),
                )
            )

        from sqlalchemy import desc

        query = query.order_by(
    desc(CatalogKey.is_active),
    desc(CatalogKey.updated_at)
)

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        items = paginated.items

        schema = CatalogKeyResponseSchema(many=True)
        data = schema.dump(items)

        # añadir user anidado
        for i, item in enumerate(items):
            data[i]["user"] = (
                {
                    "id": item.user.id,
                    "employee_id":item.user.employee_id,
                    "first_name": item.user.first_name,
                    "last_name": item.user.last_name,
                    "email": item.user.email,
                }
                if item.user
                else None
            )

        return {
            "message": "Claves de catálogo obtenidas correctamente.",
            "catalog_keys": data,
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
        Represents a catalog key that can be assigned to archival entities.

        Descripción:
            Crea una nueva clave de catálogo y la asocia al usuario autenticado
            como creador/modificador.

        Cuerpo (JSON):
            - entity_type (str, requerido): Tipo de entidad.
            - key (str, requerido): Clave única del catálogo.
            - name (str, requerido): Nombre descriptivo.
            - description (str, opcional): Descripción adicional.
            - is_active (bool, opcional): Estado inicial (por defecto True).

        Respuestas:
            201: Clave de catálogo creada.
            400: Error de validación o clave duplicada.
        """
        schema = CatalogKeyCreateSchema()
        try:
            payload = request.get_json() or {}
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        # validar clave única (solo entre no eliminadas)
        existing = (
            CatalogKey.query.filter(
                CatalogKey.key == data["key"],
                CatalogKey.deleted_at.is_(None),
            )
            .first()
        )
        if existing:
            return {"message": "La clave de catálogo ya existe."}, 400

        catalog_key = CatalogKey(
            user_id=current_user.id if current_user.is_authenticated else None,
            entity_type=data["entity_type"],
            key=data["key"],
            name=data["name"],
            description=data.get("description"),
            is_active=data.get("is_active", True),
        )

        db.session.add(catalog_key)
        db.session.commit()

        resp_schema = CatalogKeyResponseSchema()
        resp = resp_schema.dump(catalog_key)
        resp["user"] = (
            {
                "id": catalog_key.user.id,
                "first_name": catalog_key.user.first_name,
                "last_name": catalog_key.user.last_name,
                "email": catalog_key.user.email,
            }
            if catalog_key.user
            else None
        )

        return {
            "message": "Clave de catálogo creada correctamente.",
            "catalog_key": resp,
        }, 201


@api.route("/<int:key_id>")
class CatalogKeyDetail(Resource):
    @login_required
    @role_required("admin", "manager","archivist")
    def get(self, key_id: int):
        """
        Represents a catalog key that can be assigned to archival entities.

        Descripción:
            Obtiene una clave de catálogo específica por su identificador,
            siempre que no esté eliminada lógicamente.

        Parámetros de ruta:
            - key_id (int): Identificador de la clave de catálogo.

        Respuestas:
            200: Clave de catálogo encontrada.
            404: No existe o está eliminada.
        """
        catalog_key = CatalogKey.query.get(key_id)
        if not catalog_key or catalog_key.deleted_at is not None:
            return {"message": "Clave de catálogo no encontrada."}, 404

        resp_schema = CatalogKeyResponseSchema()
        resp = resp_schema.dump(catalog_key)
        resp["user"] = (
            {
                "id": catalog_key.user.id,
                "first_name": catalog_key.user.first_name,
                "last_name": catalog_key.user.last_name,
                "email": catalog_key.user.email,
            }
            if catalog_key.user
            else None
        )

        return {
            "message": "Clave de catálogo obtenida correctamente.",
            "catalog_key": resp,
        }, 200

    @login_required
    @role_required("admin", "manager","archivist")
    def put(self, key_id: int):
        """
        Represents a catalog key that can be assigned to archival entities.

        Descripción:
            Actualiza parcialmente una clave de catálogo existente. Permite cambiar
            el tipo de entidad, la clave, el nombre, la descripción y el estado.
            La modificación se registra con el usuario autenticado.

        Parámetros de ruta:
            - key_id (int): Identificador de la clave de catálogo a actualizar.

        Cuerpo (JSON):
            - entity_type (str, opcional)
            - key (str, opcional, debe ser única entre las no eliminadas)
            - name (str, opcional)
            - description (str, opcional)
            - is_active (bool, opcional)

        Respuestas:
            200: Clave de catálogo actualizada.
            400: Error de validación.
            404: Clave de catálogo no encontrada.
            409: La nueva clave ya existe en otra entrada.
        """
        schema = CatalogKeyUpdateSchema()
        try:
            payload = request.get_json() or {}
            payload["id"] = key_id
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        catalog_key = CatalogKey.query.get(key_id)
        if not catalog_key or catalog_key.deleted_at is not None:
            return {"message": "Clave de catálogo no encontrada."}, 404

        # si quiere cambiar la clave, validar que no exista en otra
        if "key" in data and data["key"] != catalog_key.key:
            existing = (
                CatalogKey.query.filter(
                    CatalogKey.key == data["key"],
                    CatalogKey.id != key_id,
                    CatalogKey.deleted_at.is_(None),
                )
                .first()
            )
            if existing:
                return {"message": "La clave de catálogo ya está en uso."}, 409
            catalog_key.key = data["key"]

        if "entity_type" in data:
            catalog_key.entity_type = data["entity_type"]
        if "name" in data:
            catalog_key.name = data["name"]
        if "description" in data:
            catalog_key.description = data["description"]
        if "is_active" in data:
            catalog_key.is_active = data["is_active"]

        # actualizar el usuario que modificó
        catalog_key.user_id = current_user.id if current_user.is_authenticated else catalog_key.user_id

        try:
            catalog_key.updated_at = db.func.now()
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al guardar en base de datos.",
                "error": str(e),
            }, 500

        resp_schema = CatalogKeyResponseSchema()
        resp = resp_schema.dump(catalog_key)
        resp["user"] = (
            {
                "id": catalog_key.user.id,
                "first_name": catalog_key.user.first_name,
                "last_name": catalog_key.user.last_name,
                "email": catalog_key.user.email,
            }
            if catalog_key.user
            else None
        )

        return {
            "message": "Clave de catálogo actualizada correctamente.",
            "catalog_key": resp,
        }, 200

    @login_required
    @role_required("admin", "manager","archivist")
    def delete(self, key_id: int):
        """
        Represents a catalog key that can be assigned to archival entities.

        Descripción:
            Realiza un borrado lógico de la clave de catálogo, marcándola como
            inactiva y registrando la fecha de eliminación.

        Parámetros de ruta:
            - key_id (int): Identificador de la clave de catálogo a eliminar.

        Respuestas:
            200: Clave de catálogo eliminada lógicamente.
            404: Clave de catálogo no encontrada.
        """
        catalog_key = CatalogKey.query.get(key_id)
        if not catalog_key or catalog_key.deleted_at is not None:
            return {"message": "Clave de catálogo no encontrada."}, 404

        catalog_key.deleted_at = db.func.now()
        catalog_key.is_active = False
        catalog_key.user_id = current_user.id if current_user.is_authenticated else catalog_key.user_id

        db.session.commit()

        return {"message": "Clave de catálogo eliminada correctamente."}, 200
