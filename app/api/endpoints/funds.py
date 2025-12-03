"""Endpoints de gestión de fondos documentales (JSON)."""

from datetime import datetime

from flask import request
from flask_login import login_required, current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.fund import Fund
from app.models.catalog_key import CatalogKey
from app.schemas.fund import (
    FundCreateSchema,
    FundUpdateSchema,
    FundResponseSchema,
)
from app.utils.security import role_required

api = Namespace(
    "funds", description="Operaciones de gestión de fondos documentales")


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
class FundList(Resource):
    @login_required
    @role_required("admin", "manager","archivist")
    def get(self):
        """
        Represents a documentary fund in the AHML Fondos system.

        Descripción:
            Obtiene una lista paginada de fondos no eliminados lógicamente,
            permitiendo filtrar por estado, usuario creador/modificador,
            clave de catálogo asociada, nombre, acrónimo y rango de fechas
            de vigencia. También permite una búsqueda libre.

        Parámetros de consulta:
            - page (int, opcional): Número de página (por defecto 1).
            - per_page (int, opcional): Tamaño de página (por defecto 20).
            - is_active (bool|str, opcional): Filtra por estado activo/inactivo ("true"/"false"/"1"/"0").
            - user_id (int, opcional): Filtra por el usuario que creó o actualizó el fondo.
            - catalog_key_id (int, opcional): Filtra por la clave de catálogo asociada.
            - name (str, opcional): Filtra por nombre parcial del fondo.
            - acronym (str, opcional): Filtra por acrónimo parcial del fondo.
            - start_date (date, opcional, formato YYYY-MM-DD): Incluye fondos cuyo start_date sea >= a este valor.
            - end_date (date, opcional, formato YYYY-MM-DD): Incluye fondos cuyo end_date sea <= a este valor.
            - query (str, opcional): Búsqueda libre aplicada sobre name y acronym.

        Respuestas:
            200: Estructura con lista de fondos y datos de paginación.
        """
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

        query = Fund.query.filter(Fund.deleted_at.is_(None))

        # filtro por estado
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ("true", "1", "yes")
            query = query.filter(Fund.is_active.is_(is_active_bool))

        # filtro por usuario
        if user_id_param:
            try:
                user_id_int = int(user_id_param)
                query = query.filter(Fund.user_id == user_id_int)
            except ValueError:
                pass

        # filtro por catalog_key
        if catalog_key_id_param:
            try:
                catalog_key_id_int = int(catalog_key_id_param)
                query = query.filter(Fund.catalog_key_id == catalog_key_id_int)
            except ValueError:
                pass

        # filtro por nombre
        if name_param:
            like_name = f"%{name_param}%"
            query = query.filter(Fund.name.ilike(like_name))

        # filtro por acrónimo
        if acronym_param:
            like_acronym = f"%{acronym_param}%"
            query = query.filter(Fund.acronym.ilike(like_acronym))

        # filtros de fecha
            # filtros de fecha
        start_date_filter = _parse_date(start_date_param)
        end_date_filter = _parse_date(end_date_param)

        # SOLO start_date → fondos donde (start >= filtro) O (end >= filtro)
        if start_date_filter and not end_date_filter:
            query = query.filter(
                or_(
                    Fund.start_date >= start_date_filter,
                    Fund.end_date >= start_date_filter
                )
            )

        # SOLO end_date → fondos donde (start <= filtro) O (end <= filtro)
        elif end_date_filter and not start_date_filter:
            query = query.filter(
                or_(
                    Fund.start_date <= end_date_filter,
                    Fund.end_date <= end_date_filter
                )
            )

        # AMBOS → fondos cuyo rango intersecta el rango solicitado
        elif start_date_filter and end_date_filter:
            query = query.filter(
                Fund.start_date <= end_date_filter,
                Fund.end_date >= start_date_filter
            )

        # búsqueda libre
        # búsqueda libre
        if query_param:
            like = f"%{query_param}%"
            query = query.filter(
                or_(
                    Fund.name.ilike(like),
                    Fund.acronym.ilike(like),
                    CatalogKey.key.ilike(like),
                    CatalogKey.name.ilike(like),
                )
            )

        # orden
        # query = query.order_by(Fund.updated_at.desc())
        from sqlalchemy import desc

        query = query.order_by(
            desc(Fund.is_active),
            desc(Fund.updated_at))

        paginated = query.paginate(
            page=page, per_page=per_page, error_out=False)
        items = paginated.items

        schema = FundResponseSchema(many=True)
        data = schema.dump(items)

        # anidar user y catalog_key
        for i, item in enumerate(items):
            data[i]["user"] = (
                {
                    "id": item.user.id,
                    "employee_id": item.user.employee_id,
                    "first_name": item.user.first_name,
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
            "message": "Fondos obtenidos correctamente.",
            "funds": data,
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
        Represents a documentary fund in the AHML Fondos system.

        Descripción:
            Crea un nuevo fondo documental y lo asocia al usuario autenticado
            como creador/modificador. Si se envía un catalog_key_id, se valida
            que:
                1) exista,
                2) no esté eliminada (deleted_at == NULL),
                3) esté activa (is_active == TRUE),
                4) su entity_type sea 'fund'.
            Si algo de eso falla, se rechaza.

        Cuerpo (JSON):
            - catalog_key_id (int, opcional): ID de la clave de catálogo asociada. Debe ser de tipo 'fund' y estar activa.
            - name (str, requerido): Nombre del fondo.
            - acronym (str, opcional): Acrónimo del fondo.
            - start_date (str, opcional, formato YYYY-MM-DD): Fecha de inicio de vigencia.
            - end_date (str, opcional, formato YYYY-MM-DD): Fecha de fin de vigencia.
            - is_active (bool, opcional): Estado inicial del fondo (por defecto True).

        Respuestas:
            201: Fondo creado correctamente.
            400: Error de validación o la catalog_key no es válida/activa/del tipo correcto.
        """
        schema = FundCreateSchema()
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
                    "message": "La clave de catálogo está inactiva y no puede usarse en un fondo."
                }, 400

            if ck.entity_type != "fund":
                return {
                    "message": "La clave de catálogo no es del tipo adecuado para un fondo.",
                    "expected_entity_type": "fund",
                    "found_entity_type": ck.entity_type,
                }, 400

        fund = Fund(
            catalog_key_id=catalog_key_id,
            user_id=current_user.id if current_user.is_authenticated else None,
            name=data["name"],
            acronym=data.get("acronym"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            is_active=data.get("is_active", True),
        )

        db.session.add(fund)
        db.session.commit()

        resp_schema = FundResponseSchema()
        resp = resp_schema.dump(fund)
        resp["user"] = (
            {
                "id": fund.user.id,
                "first_name": fund.user.first_name,
                "last_name": fund.user.last_name,
                "email": fund.user.email,
            }
            if fund.user
            else None
        )
        resp["catalog_key"] = (
            {
                "id": fund.catalog_key.id,
                "key": fund.catalog_key.key,
                "name": fund.catalog_key.name,
            }
            if fund.catalog_key
            else None
        )

        return {
            "message": "Fondo creado correctamente.",
            "fund": resp,
        }, 201


@api.route("/<int:fund_id>")
class FundDetail(Resource):
    @login_required
    @role_required("admin", "manager")
    def get(self, fund_id: int):
        """
        Represents a documentary fund in the AHML Fondos system.

        Descripción:
            Obtiene un fondo documental por su identificador, incluyendo los datos
            del usuario que lo creó/modificó y la clave de catálogo asociada.

        Parámetros de ruta:
            - fund_id (int): Identificador del fondo documental.

        Respuestas:
            200: Fondo obtenido correctamente.
            404: Fondo no encontrado o eliminado lógicamente.
        """
        fund = Fund.query.get(fund_id)
        if not fund or fund.deleted_at is not None:
            return {"message": "Fondo no encontrado."}, 404

        resp_schema = FundResponseSchema()
        resp = resp_schema.dump(fund)
        resp["user"] = (
            {
                "id": fund.user.id,
                "first_name": fund.user.first_name,
                "last_name": fund.user.last_name,
                "email": fund.user.email,
            }
            if fund.user
            else None
        )
        resp["catalog_key"] = (
            {
                "id": fund.catalog_key.id,
                "key": fund.catalog_key.key,
                "name": fund.catalog_key.name,
            }
            if fund.catalog_key
            else None
        )

        return {
            "message": "Fondo obtenido correctamente.",
            "fund": resp,
        }, 200

    @login_required
    @role_required("admin", "manager")
    def put(self, fund_id: int):
        """
        Represents a documentary fund in the AHML Fondos system.

        Descripción:
            Actualiza parcialmente un fondo documental existente. Permite modificar
            el nombre, acrónimo, fechas de vigencia, estado y la clave de catálogo
            asociada. Si se cambia la clave de catálogo, se valida que:
                1) exista,
                2) no esté eliminada,
                3) esté activa,
                4) sea de tipo 'fund'.
            La actualización registra al usuario que hizo el cambio.

        Parámetros de ruta:
            - fund_id (int): Identificador del fondo a actualizar.

        Cuerpo (JSON):
            - catalog_key_id (int, opcional): Nueva clave de catálogo (debe ser de tipo 'fund', activa y no eliminada).
            - name (str, opcional): Nuevo nombre del fondo.
            - acronym (str, opcional): Nuevo acrónimo del fondo.
            - start_date (str, opcional, formato YYYY-MM-DD): Nueva fecha de inicio.
            - end_date (str, opcional, formato YYYY-MM-DD): Nueva fecha de fin.
            - is_active (bool, opcional): Nuevo estado del fondo.

        Respuestas:
            200: Fondo actualizado correctamente.
            400: Error de validación o clave de catálogo inválida/inactiva/eliminada o de tipo incorrecto.
            404: Fondo no encontrado.
        """
        schema = FundUpdateSchema()
        try:
            payload = request.get_json() or {}
            payload["id"] = fund_id
            data = schema.load(payload)
        except ValidationError as err:
            return {"message": "Error de validación.", "errors": err.messages}, 400

        fund = Fund.query.get(fund_id)
        if not fund or fund.deleted_at is not None:
            return {"message": "Fondo no encontrado."}, 404

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
                        "message": "La clave de catálogo está inactiva y no puede usarse en un fondo."
                    }, 400

                if ck.entity_type != "fund":
                    return {
                        "message": "La clave de catálogo no es del tipo adecuado para un fondo.",
                        "expected_entity_type": "fund",
                        "found_entity_type": ck.entity_type,
                    }, 400

            fund.catalog_key_id = ck_id

        if "name" in data:
            fund.name = data["name"]
        if "acronym" in data:
            fund.acronym = data["acronym"]
        if "start_date" in data:
            fund.start_date = data["start_date"]
        if "end_date" in data:
            fund.end_date = data["end_date"]
        if "is_active" in data:
            fund.is_active = data["is_active"]

        # registrar quién modificó
        fund.user_id = current_user.id if current_user.is_authenticated else fund.user_id

        try:
            fund.updated_at = db.func.now()
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al guardar en base de datos.",
                "error": str(e),
            }, 500

        resp_schema = FundResponseSchema()
        resp = resp_schema.dump(fund)
        resp["user"] = (
            {
                "id": fund.user.id,
                "first_name": fund.user.first_name,
                "last_name": fund.user.last_name,
                "email": fund.user.email,
            }
            if fund.user
            else None
        )
        resp["catalog_key"] = (
            {
                "id": fund.catalog_key.id,
                "key": fund.catalog_key.key,
                "name": fund.catalog_key.name,
            }
            if fund.catalog_key
            else None
        )

        return {
            "message": "Fondo actualizado correctamente.",
            "fund": resp,
        }, 200

    @login_required
    @role_required("admin", "manager")
    def delete(self, fund_id: int):
        """
        Represents a documentary fund in the AHML Fondos system.

        Descripción:
            Realiza un borrado lógico del fondo documental, marcándolo como inactivo
            y registrando la fecha de eliminación. No elimina físicamente el registro.

        Parámetros de ruta:
            - fund_id (int): Identificador del fondo a eliminar.

        Respuestas:
            200: Fondo eliminado lógicamente.
            404: Fondo no encontrado.
        """
        fund = Fund.query.get(fund_id)
        if not fund or fund.deleted_at is not None:
            return {"message": "Fondo no encontrado."}, 404

        fund.deleted_at = db.func.now()
        fund.is_active = False
        fund.user_id = current_user.id if current_user.is_authenticated else fund.user_id

        db.session.commit()

        return {"message": "Fondo eliminado correctamente."}, 200
