"""Endpoints de gestión de secciones administrativas (JSON)."""

from datetime import datetime

from flask import request
from flask_login import login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.section import Section
from app.models.catalog_key import CatalogKey
from app.schemas.section import (
    SectionCreateSchema,
    SectionUpdateSchema,
    SectionResponseSchema,
)
from app.utils.security import role_required

api = Namespace("sections", description="Operaciones de gestión de secciones administrativas")


def _parse_date(date_str: str):
    """Acepta formatos YYYY-MM-DD y DD-MM-YYYY."""
    if not date_str:
        return None

    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            pass

    return None


@api.route("")
class SectionList(Resource):
    @login_required
    @role_required("admin", "manager")
    def get(self):
        is_active_param = request.args.get("is_active")
        user_id_param = request.args.get("user_id")
        catalog_key_id_param = request.args.get("catalog_key_id")
        name_param = request.args.get("name", "").strip()
        acronym_param = request.args.get("acronym", "").strip()
        query_param = request.args.get("query", "").strip()
        start_date_param = request.args.get("start_date")
        end_date_param = request.args.get("end_date")

        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 20))
        except ValueError:
            page = 1
            per_page = 20

        query = Section.query.filter(Section.deleted_at.is_(None))

        # estado
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ("true", "1", "yes")
            query = query.filter(Section.is_active.is_(is_active_bool))

        # usuario
        if user_id_param:
            try:
                user_id_int = int(user_id_param)
                query = query.filter(Section.user_id == user_id_int)
            except ValueError:
                pass

        # catalog_key_id directo
        if catalog_key_id_param:
            try:
                ck_id_int = int(catalog_key_id_param)
                query = query.filter(Section.catalog_key_id == ck_id_int)
            except ValueError:
                pass

        # nombre
        if name_param:
            like_name = f"%{name_param}%"
            query = query.filter(Section.name.ilike(like_name))

        # acrónimo
        if acronym_param:
            like_acronym = f"%{acronym_param}%"
            query = query.filter(Section.acronym.ilike(like_acronym))

        # fechas usando lógica igual a fondos
        start_date_filter = _parse_date(start_date_param)
        end_date_filter = _parse_date(end_date_param)

        # SOLO start_date
        if start_date_filter and not end_date_filter:
            query = query.filter(
                or_(
                    Section.start_date >= start_date_filter,
                    Section.end_date >= start_date_filter,
                )
            )

        # SOLO end_date
        elif end_date_filter and not start_date_filter:
            query = query.filter(
                or_(
                    Section.start_date <= end_date_filter,
                    Section.end_date <= end_date_filter,
                )
            )

        # AMBOS → rango que intersecta
        elif start_date_filter and end_date_filter:
            query = query.filter(
                Section.start_date <= end_date_filter,
                Section.end_date >= start_date_filter,
            )

        # búsqueda libre (name, acronym, key.key, key.name)
        if query_param:
            like = f"%{query_param}%"
            query = query.filter(
                or_(
                    Section.name.ilike(like),
                    Section.acronym.ilike(like),
                    CatalogKey.key.ilike(like),
                    CatalogKey.name.ilike(like),
                )
            )

        # ORDENO por estado y updated_at DESC igual que fondos
        from sqlalchemy import desc
        query = query.order_by(
            desc(Section.is_active),
            desc(Section.updated_at)
        )

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        items = paginated.items

        schema = SectionResponseSchema(many=True)
        data = schema.dump(items)

        # anidar user y catalog_key
        for i, item in enumerate(items):
            data[i]["user"] = (
                {
                    "id": item.user.id,
                    "first_name": item.user.first_name,
                    "employee_id": item.user.employee_id,
                    "last_name": item.user.last_name,
                    "email": item.user.email,
                }
                if item.user else None
            )
            data[i]["catalog_key"] = (
                {
                    "id": item.catalog_key.id,
                    "key": item.catalog_key.key,
                    "name": item.catalog_key.name,
                }
                if item.catalog_key else None
            )

        return {
            "message": "Secciones obtenidas correctamente.",
            "sections": data,
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
        Represents an administrative/organizational section in the AHML Fondos system.

        Descripción:
            Crea una nueva sección administrativa y la asocia al usuario autenticado
            como creador/modificador. Si se envía un catalog_key_id, se valida que:
                1) exista,
                2) no esté eliminada (deleted_at == NULL),
                3) esté activa (is_active == TRUE),
                4) sea del tipo 'section'.
            Si no cumple alguno de los puntos anteriores, se rechaza.

        Cuerpo (JSON):
            - catalog_key_id (int, opcional): ID de la clave de catálogo asociada. Debe ser de tipo 'section' y estar activa.
            - name (str, requerido): Nombre de la sección.
            - acronym (str, opcional): Acrónimo de la sección.
            - start_date (str, opcional, formato YYYY-MM-DD): Fecha de inicio de vigencia.
            - end_date (str, opcional, formato YYYY-MM-DD): Fecha de fin de vigencia.
            - is_active (bool, opcional): Estado inicial (por defecto True).

        Respuestas:
            201: Sección creada correctamente.
            400: Error de validación o catalog key inexistente/inactiva/de tipo incorrecto.
        """
        schema = SectionCreateSchema()
        try:
            payload = request.get_json() or {}
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        catalog_key_id = data.get("catalog_key_id")
        if catalog_key_id:
            ck = CatalogKey.query.filter(
                CatalogKey.id == catalog_key_id,
                # este filter ya exige que deleted_at sea NULL
                CatalogKey.deleted_at.is_(None),
            ).first()
            if not ck:
                return {"message": "La clave de catálogo especificada no existe o está eliminada."}, 400

            # nueva validación: debe estar activa
            if not ck.is_active:
                return {
                    "message": "La clave de catálogo está inactiva y no puede usarse en una sección."
                }, 400

            if ck.entity_type != "section":
                return {
                    "message": "La clave de catálogo no es del tipo adecuado para una sección.",
                    "expected_entity_type": "section",
                    "found_entity_type": ck.entity_type,
                }, 400

        section = Section(
            catalog_key_id=catalog_key_id,
            user_id=current_user.id if current_user.is_authenticated else None,
            name=data["name"],
            acronym=data.get("acronym"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            is_active=data.get("is_active", True),
        )

        db.session.add(section)
        db.session.commit()

        resp_schema = SectionResponseSchema()
        resp = resp_schema.dump(section)
        resp["user"] = (
            {
                "id": section.user.id,
                "first_name": section.user.first_name,
                "last_name": section.user.last_name,
                "email": section.user.email,
            }
            if section.user
            else None
        )
        resp["catalog_key"] = (
            {
                "id": section.catalog_key.id,
                "key": section.catalog_key.key,
                "name": section.catalog_key.name,
            }
            if section.catalog_key
            else None
        )

        return {
            "message": "Sección creada correctamente.",
            "section": resp,
        }, 201


@api.route("/<int:section_id>")
class SectionDetail(Resource):
    @login_required
    @role_required("admin", "manager")
    def get(self, section_id: int):
        """
        Represents an administrative/organizational section in the AHML Fondos system.

        Descripción:
            Obtiene una sección administrativa por su identificador, incluyendo los datos
            del usuario que la creó/modificó y la clave de catálogo asociada.

        Parámetros de ruta:
            - section_id (int): Identificador de la sección.

        Respuestas:
            200: Sección obtenida correctamente.
            404: Sección no encontrada o eliminada lógicamente.
        """
        section = Section.query.get(section_id)
        if not section or section.deleted_at is not None:
            return {"message": "Sección no encontrada."}, 404

        resp_schema = SectionResponseSchema()
        resp = resp_schema.dump(section)
        resp["user"] = (
            {
                "id": section.user.id,
                "first_name": section.user.first_name,
                "last_name": section.user.last_name,
                "email": section.user.email,
            }
            if section.user
            else None
        )
        resp["catalog_key"] = (
            {
                "id": section.catalog_key.id,
                "key": section.catalog_key.key,
                "name": section.catalog_key.name,
            }
            if section.catalog_key
            else None
        )

        return {
            "message": "Sección obtenida correctamente.",
            "section": resp,
        }, 200

    @login_required
    @role_required("admin", "manager")
    def put(self, section_id: int):
        """
        Represents an administrative/organizational section in the AHML Fondos system.

        Descripción:
            Actualiza parcialmente una sección administrativa existente. Permite modificar
            el nombre, acrónimo, fechas de vigencia, estado y la clave de catálogo asociada.
            Si se cambia la clave de catálogo, se valida que:
                1) exista,
                2) no esté eliminada (deleted_at == NULL),
                3) esté activa (is_active == TRUE),
                4) sea de tipo 'section'.
            La modificación se registra con el usuario autenticado.

        Parámetros de ruta:
            - section_id (int): Identificador de la sección a actualizar.

        Cuerpo (JSON):
            - catalog_key_id (int, opcional): Nueva clave de catálogo (debe ser de tipo 'section', activa y no eliminada).
            - name (str, opcional): Nuevo nombre de la sección.
            - acronym (str, opcional): Nuevo acrónimo de la sección.
            - start_date (str, opcional, formato YYYY-MM-DD): Nueva fecha de inicio de vigencia.
            - end_date (str, opcional, formato YYYY-MM-DD): Nueva fecha de fin de vigencia.
            - is_active (bool, opcional): Nuevo estado de la sección.

        Respuestas:
            200: Sección actualizada correctamente.
            400: Error de validación o clave de catálogo inválida/inactiva/eliminada o de tipo incorrecto.
            404: Sección no encontrada.
        """
        schema = SectionUpdateSchema()
        try:
            payload = request.get_json() or {}
            payload["id"] = section_id
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        section = Section.query.get(section_id)
        if not section or section.deleted_at is not None:
            return {"message": "Sección no encontrada."}, 404

        # cambio de catalog_key
        if "catalog_key_id" in data:
            ck_id = data["catalog_key_id"]
            if ck_id is not None:
                ck = CatalogKey.query.filter(
                    CatalogKey.id == ck_id,
                    CatalogKey.deleted_at.is_(None),
                ).first()
                if not ck:
                    return {"message": "La clave de catálogo especificada no existe o está eliminada."}, 400

                if not ck.is_active:
                    return {
                        "message": "La clave de catálogo está inactiva y no puede usarse en una sección."
                    }, 400

                if ck.entity_type != "section":
                    return {
                        "message": "La clave de catálogo no es del tipo adecuado para una sección.",
                        "expected_entity_type": "section",
                        "found_entity_type": ck.entity_type,
                    }, 400

            section.catalog_key_id = ck_id

        if "name" in data:
            section.name = data["name"]
        if "acronym" in data:
            section.acronym = data["acronym"]
        if "start_date" in data:
            section.start_date = data["start_date"]
        if "end_date" in data:
            section.end_date = data["end_date"]
        if "is_active" in data:
            section.is_active = data["is_active"]

        # registrar quién modificó
        section.user_id = current_user.id if current_user.is_authenticated else section.user_id

        try:
            section.updated_at = db.func.now()
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al guardar en base de datos.",
                "error": str(e),
            }, 500

        resp_schema = SectionResponseSchema()
        resp = resp_schema.dump(section)
        resp["user"] = (
            {
                "id": section.user.id,
                "first_name": section.user.first_name,
                "last_name": section.user.last_name,
                "email": section.user.email,
            }
            if section.user
            else None
        )
        resp["catalog_key"] = (
            {
                "id": section.catalog_key.id,
                "key": section.catalog_key.key,
                "name": section.catalog_key.name,
            }
            if section.catalog_key
            else None
        )

        return {
            "message": "Sección actualizada correctamente.",
            "section": resp,
        }, 200

    @login_required
    @role_required("admin", "manager")
    def delete(self, section_id: int):
        """
        Represents an administrative/organizational section in the AHML Fondos system.

        Descripción:
            Realiza un borrado lógico de la sección, marcándola como inactiva y registrando
            la fecha de eliminación. No elimina físicamente el registro.

        Parámetros de ruta:
            - section_id (int): Identificador de la sección a eliminar.

        Respuestas:
            200: Sección eliminada lógicamente.
            404: Sección no encontrada.
        """
        section = Section.query.get(section_id)
        if not section or section.deleted_at is not None:
            return {"message": "Sección no encontrada."}, 404

        section.deleted_at = db.func.now()
        section.is_active = False
        section.user_id = current_user.id if current_user.is_authenticated else section.user_id

        db.session.commit()

        return {"message": "Sección eliminada correctamente."}, 200
