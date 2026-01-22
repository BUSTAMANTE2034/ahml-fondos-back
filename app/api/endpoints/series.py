"""Endpoints de gestión de series documentales (JSON)."""

from datetime import datetime

from flask import request
from flask_login import login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.series import Series
from app.models.catalog_key import CatalogKey
from app.schemas.series import (
    SeriesCreateSchema,
    SeriesUpdateSchema,
    SeriesResponseSchema,
)
from app.utils.security import role_required
from sqlalchemy import asc, desc
api = Namespace("series", description="Operaciones de gestión de series documentales")


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

def _apply_series_ordering(query, order_by_param: str):
    """
    Aplica ordenamiento al query de Series.

    order_by soportado:
        - created_at_asc / created_at_desc
        - updated_at_asc / updated_at_desc
        - start_date_asc / start_date_desc
        - end_date_asc / end_date_desc
        - name_asc / name_desc
        - acronym_asc / acronym_desc
    """

    # -----------------------------
    # Orden por defecto
    # -----------------------------
    if not order_by_param:
        return query.order_by(Series.updated_at.desc())

    mapping = {
        # Fechas
        "created_at_asc": Series.created_at.asc(),
        "created_at_desc": Series.created_at.desc(),

        "updated_at_asc": Series.updated_at.asc(),
        "updated_at_desc": Series.updated_at.desc(),

        "start_date_asc": Series.start_date.asc(),
        "start_date_desc": Series.start_date.desc(),

        "end_date_asc": Series.end_date.asc(),
        "end_date_desc": Series.end_date.desc(),

        # Texto
        "name_asc": Series.name.asc(),
        "name_desc": Series.name.desc(),

        "acronym_asc": Series.acronym.asc(),
        "acronym_desc": Series.acronym.desc(),
    }

    sort_expr = mapping.get(order_by_param)

    # Fallback seguro
    if sort_expr is None:
        return query.order_by(Series.updated_at.desc())

    return query.order_by(sort_expr)

@api.route("")
class SeriesList(Resource):
    @login_required
    @role_required("admin", "manager","archivist")
    def get(self):
        is_active_param = request.args.get("is_active")
        user_id_param = request.args.get("user_id")
        catalog_key_id_param = request.args.get("catalog_key_id")
        name_param = request.args.get("name", "").strip()
        acronym_param = request.args.get("acronym", "").strip()
        query_param = request.args.get("query", "").strip()
        start_date_param = request.args.get("start_date")
        end_date_param = request.args.get("end_date")
        order_by_param = request.args.get("order_by")

        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 20))
        except ValueError:
            page = 1
            per_page = 20

        query = Series.query.filter(Series.deleted_at.is_(None))

        # estado
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ("true", "1", "yes")
            query = query.filter(Series.is_active.is_(is_active_bool))

        # usuario
        if user_id_param:
            try:
                user_id_int = int(user_id_param)
                query = query.filter(Series.user_id == user_id_int)
            except ValueError:
                pass

        # catalog key
        if catalog_key_id_param:
            try:
                ck_id_int = int(catalog_key_id_param)
                query = query.filter(Series.catalog_key_id == ck_id_int)
            except ValueError:
                pass

        # nombre
        if name_param:
            like_name = f"%{name_param}%"
            query = query.filter(Series.name.ilike(like_name))

        # acrónimo
        if acronym_param:
            like_acronym = f"%{acronym_param}%"
            query = query.filter(Series.acronym.ilike(like_acronym))

        # fechas — mismo comportamiento que FONDOS y SECCIONES
        start_date_filter = _parse_date(start_date_param)
        end_date_filter = _parse_date(end_date_param)

        # SOLO start_date
        if start_date_filter and not end_date_filter:
            query = query.filter(
                or_(
                    Series.start_date >= start_date_filter,
                    Series.end_date >= start_date_filter,
                )
            )

        # SOLO end_date
        elif end_date_filter and not start_date_filter:
            query = query.filter(
                or_(
                    Series.start_date <= end_date_filter,
                    Series.end_date <= end_date_filter,
                )
            )

        # AMBOS → rangos que se intersecten
        elif start_date_filter and end_date_filter:
            query = query.filter(
                Series.start_date <= end_date_filter,
                Series.end_date >= start_date_filter,
            )

        # búsqueda libre con catalog_key
        if query_param:
            like = f"%{query_param}%"
            query = query.join(CatalogKey, isouter=True).filter(
                or_(
                    Series.name.ilike(like),
                    Series.acronym.ilike(like),
                    CatalogKey.key.ilike(like),
                    CatalogKey.name.ilike(like),
                )
            )

        # orden
        query = _apply_series_ordering(query, order_by_param)
        

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        items = paginated.items

        schema = SeriesResponseSchema(many=True)
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
                if item.user
                else None
            )
            data[i]["catalog_key"] = (
                {
                    "id": item.catalog_key.id,
                    "key": item.catalog_key.key,
                    "name": item.catalog_key.name,
                }
                if item.catalog_key
                else None
            )

        return {
            "message": "Series obtenidas correctamente.",
            "series": data,
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
        Represents a documentary series in the AHML Fondos system.

        Descripción:
            Crea una nueva serie documental y la asocia al usuario autenticado
            como creador/modificador. Si se envía un catalog_key_id, se valida
            que:
                1) exista,
                2) no esté eliminada (deleted_at == NULL),
                3) esté activa (is_active == TRUE),
                4) su entity_type sea 'series'.
            Si algo de eso falla, se rechaza.

        Cuerpo (JSON):
            - catalog_key_id (int, opcional): ID de la clave de catálogo asociada. Debe ser de tipo 'series' y estar activa.
            - name (str, requerido): Nombre de la serie.
            - acronym (str, opcional): Acrónimo de la serie.
            - start_date (str, opcional, formato YYYY-MM-DD): Fecha de inicio de vigencia.
            - end_date (str, opcional, formato YYYY-MM-DD): Fecha de fin de vigencia.
            - is_active (bool, opcional): Estado inicial (por defecto True).

        Respuestas:
            201: Serie creada correctamente.
            400: Error de validación o catalog key inválida/inactiva/de tipo incorrecto.
        """
        schema = SeriesCreateSchema()
        try:
            payload = request.get_json() or {}
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        catalog_key_id = data.get("catalog_key_id")
        if catalog_key_id:
            ck = CatalogKey.query.filter(
                CatalogKey.id == catalog_key_id,
                CatalogKey.deleted_at.is_(None),
            ).first()
            if not ck:
                return {
                    "message": "La clave de catálogo especificada no existe o está eliminada."
                }, 400

            if not ck.is_active:
                return {
                    "message": "La clave de catálogo está inactiva y no puede usarse en una serie."
                }, 400

            if ck.entity_type != "series":
                return {
                    "message": "La clave de catálogo no es del tipo adecuado para una serie.",
                    "expected_entity_type": "series",
                    "found_entity_type": ck.entity_type,
                }, 400

        series = Series(
            catalog_key_id=catalog_key_id,
            user_id=current_user.id if current_user.is_authenticated else None,
            name=data["name"],
            acronym=data.get("acronym"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            is_active=data.get("is_active", True),
        )

        db.session.add(series)
        db.session.commit()

        resp_schema = SeriesResponseSchema()
        resp = resp_schema.dump(series)
        resp["user"] = (
            {
                "id": series.user.id,
                "first_name": series.user.first_name,
                "last_name": series.user.last_name,
                "email": series.user.email,
            }
            if series.user
            else None
        )
        resp["catalog_key"] = (
            {
                "id": series.catalog_key.id,
                "key": series.catalog_key.key,
                "name": series.catalog_key.name,
            }
            if series.catalog_key
            else None
        )

        return {
            "message": "Serie creada correctamente.",
            "series": resp,
        }, 201


@api.route("/<int:series_id>")
class SeriesDetail(Resource):
    @login_required
    @role_required("admin", "manager","archivist")
    def get(self, series_id: int):
        """
        Represents a documentary series in the AHML Fondos system.

        Descripción:
            Obtiene una serie documental por su identificador, incluyendo los datos
            del usuario que la creó/modificó y la clave de catálogo asociada.

        Parámetros de ruta:
            - series_id (int): Identificador de la serie.

        Respuestas:
            200: Serie obtenida correctamente.
            404: Serie no encontrada o eliminada lógicamente.
        """
        series = Series.query.get(series_id)
        if not series or series.deleted_at is not None:
            return {"message": "Serie no encontrada."}, 404

        resp_schema = SeriesResponseSchema()
        resp = resp_schema.dump(series)
        resp["user"] = (
            {
                "id": series.user.id,
                "first_name": series.user.first_name,
                "last_name": series.user.last_name,
                "email": series.user.email,
            }
            if series.user
            else None
        )
        resp["catalog_key"] = (
            {
                "id": series.catalog_key.id,
                "key": series.catalog_key.key,
                "name": series.catalog_key.name,
            }
            if series.catalog_key
            else None
        )

        return {
            "message": "Serie obtenida correctamente.",
            "series": resp,
        }, 200

    @login_required
    @role_required("admin", "manager","archivist")
    def put(self, series_id: int):
        """
        Represents a documentary series in the AHML Fondos system.

        Descripción:
            Actualiza parcialmente una serie documental existente. Permite modificar
            el nombre, acrónimo, fechas de vigencia, estado y la clave de catálogo
            asociada. Si se cambia la clave de catálogo, se valida que:
                1) exista,
                2) no esté eliminada,
                3) esté activa,
                4) sea de tipo 'series'.
            La actualización registra al usuario que hizo el cambio.

        Parámetros de ruta:
            - series_id (int): Identificador de la serie a actualizar.

        Cuerpo (JSON):
            - catalog_key_id (int, opcional): Nueva clave de catálogo (debe ser de tipo 'series', activa y no eliminada).
            - name (str, opcional): Nuevo nombre de la serie.
            - acronym (str, opcional): Nuevo acrónimo de la serie.
            - start_date (str, opcional, formato YYYY-MM-DD): Nueva fecha de inicio.
            - end_date (str, opcional, formato YYYY-MM-DD): Nueva fecha de fin.
            - is_active (bool, opcional): Nuevo estado de la serie.

        Respuestas:
            200: Serie actualizada correctamente.
            400: Error de validación o clave de catálogo inválida/inactiva/eliminada o de tipo incorrecto.
            404: Serie no encontrada.
        """
        schema = SeriesUpdateSchema()
        try:
            payload = request.get_json() or {}
            payload["id"] = series_id
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        series = Series.query.get(series_id)
        if not series or series.deleted_at is not None:
            return {"message": "Serie no encontrada."}, 404

        # cambio de catalog_key
        if "catalog_key_id" in data:
            ck_id = data["catalog_key_id"]
            if ck_id is not None:
                ck = CatalogKey.query.filter(
                    CatalogKey.id == ck_id,
                    CatalogKey.deleted_at.is_(None),
                ).first()
                if not ck:
                    return {
                        "message": "La clave de catálogo especificada no existe o está eliminada."
                    }, 400

                if not ck.is_active:
                    return {
                        "message": "La clave de catálogo está inactiva y no puede usarse en una serie."
                    }, 400

                if ck.entity_type != "series":
                    return {
                        "message": "La clave de catálogo no es del tipo adecuado para una serie.",
                        "expected_entity_type": "series",
                        "found_entity_type": ck.entity_type,
                    }, 400

            series.catalog_key_id = ck_id

        if "name" in data:
            series.name = data["name"]
        if "acronym" in data:
            series.acronym = data["acronym"]
        if "start_date" in data:
            series.start_date = data["start_date"]
        if "end_date" in data:
            series.end_date = data["end_date"]
        if "is_active" in data:
            series.is_active = data["is_active"]

        # registrar quién modificó
        series.user_id = current_user.id if current_user.is_authenticated else series.user_id

        try:
            series.updated_at = db.func.now()
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al guardar en base de datos.",
                "error": str(e),
            }, 500

        resp_schema = SeriesResponseSchema()
        resp = resp_schema.dump(series)
        resp["user"] = (
            {
                "id": series.user.id,
                "first_name": series.user.first_name,
                "last_name": series.user.last_name,
                "email": series.user.email,
            }
            if series.user
            else None
        )
        resp["catalog_key"] = (
            {
                "id": series.catalog_key.id,
                "key": series.catalog_key.key,
                "name": series.catalog_key.name,
            }
            if series.catalog_key
            else None
        )

        return {
            "message": "Serie actualizada correctamente.",
            "series": resp,
        }, 200

    @login_required
    @role_required("admin", "manager","archivist")
    def delete(self, series_id: int):
        """
        Represents a documentary series in the AHML Fondos system.

        Descripción:
            Realiza un borrado lógico de la serie documental, marcándola como inactiva
            y registrando la fecha de eliminación. No elimina físicamente el registro.

        Parámetros de ruta:
            - series_id (int): Identificador de la serie a eliminar.

        Respuestas:
            200: Serie eliminada lógicamente.
            404: Serie no encontrada.
        """
        series = Series.query.get(series_id)
        if not series or series.deleted_at is not None:
            return {"message": "Serie no encontrada."}, 404

        series.deleted_at = db.func.now()
        series.is_active = False
        series.user_id = current_user.id if current_user.is_authenticated else series.user_id

        db.session.commit()

        return {"message": "Serie eliminada correctamente."}, 200
