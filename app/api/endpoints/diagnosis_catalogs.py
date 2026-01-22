"""
Endpoints de gestión del Catálogo de Diagnóstico (Conceptos y Detalles).

Permite administrar los conceptos y detalles utilizados en la revisión
técnica de expedientes documentales.
"""

from flask import request
from flask_login import login_required,current_user
from flask_restx import Resource, Namespace
from marshmallow import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.diagnosis_catalog import DiagnosisCatalog
from app.schemas.diagnosis_catalog import (
    DiagnosisCatalogCreateSchema,
    DiagnosisCatalogUpdateSchema,
    DiagnosisCatalogResponseSchema,
)
from app.utils.security import role_required
from sqlalchemy import desc
api = Namespace(
    "diagnosis_catalog",
    description="Operaciones de gestión del catálogo de diagnóstico",
)


def _apply_diagnosis_catalog_ordering(query, order_by_param: str):
    """
    Aplica ordenamiento al query de DiagnosisCatalog.

    order_by soportado:
        - concept_asc / concept_desc
        - detail_asc / detail_desc
        - description_asc / description_desc
        - created_at_asc / created_at_desc
        - updated_at_asc / updated_at_desc
    """

    # -----------------------------
    # Orden por defecto
    # -----------------------------
    if not order_by_param:
        return query.order_by(
            DiagnosisCatalog.is_active.desc(),
            DiagnosisCatalog.updated_at.desc(),
        )

    mapping = {
        # Texto
        "concept_asc": DiagnosisCatalog.concept.asc(),
        "concept_desc": DiagnosisCatalog.concept.desc(),

        "detail_asc": DiagnosisCatalog.detail.asc(),
        "detail_desc": DiagnosisCatalog.detail.desc(),

        "description_asc": DiagnosisCatalog.description.asc(),
        "description_desc": DiagnosisCatalog.description.desc(),

        # Fechas
        "created_at_asc": DiagnosisCatalog.created_at.asc(),
        "created_at_desc": DiagnosisCatalog.created_at.desc(),

        "updated_at_asc": DiagnosisCatalog.updated_at.asc(),
        "updated_at_desc": DiagnosisCatalog.updated_at.desc(),
    }

    sort_expr = mapping.get(order_by_param)

    # Fallback seguro
    if sort_expr is None:
        return query.order_by(
            DiagnosisCatalog.is_active.desc(),
            DiagnosisCatalog.updated_at.desc(),
        )

    # Activos primero + orden solicitado
    return query.order_by(
        DiagnosisCatalog.is_active.desc(),
        sort_expr
    )

@api.route("")
class DiagnosisCatalogList(Resource):

    @login_required
    @role_required("admin", "manager", "archivist")
    def get(self):
        """
        Obtiene lista paginada del catálogo de diagnóstico no eliminado lógicamente,
        con filtros por concepto, detalle, estado y búsqueda libre.
        """
        concept_param = request.args.get("concept", "").strip()
        detail_param = request.args.get("detail", "").strip()
        is_active_param = request.args.get("is_active")
        query_param = request.args.get("query", "").strip()
        order_by_param = request.args.get("order_by")

        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 20))
        except ValueError:
            page = 1
            per_page = 20

        query = DiagnosisCatalog.query.filter(
            DiagnosisCatalog.deleted_at.is_(None)
        )

        # filtro por estado
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ("true", "1", "yes")
            query = query.filter(DiagnosisCatalog.is_active.is_(is_active_bool))

        # filtro por concepto
        if concept_param:
            like = f"%{concept_param}%"
            query = query.filter(DiagnosisCatalog.concept.ilike(like))

        # filtro por detalle
        if detail_param:
            like = f"%{detail_param}%"
            query = query.filter(DiagnosisCatalog.detail.ilike(like))

        # búsqueda libre
        if query_param:
            like = f"%{query_param}%"
            query = query.filter(
                or_(
                    DiagnosisCatalog.concept.ilike(like),
                    DiagnosisCatalog.detail.ilike(like),
                    DiagnosisCatalog.description.ilike(like),
                )
            )

        query = _apply_diagnosis_catalog_ordering(query, order_by_param)

        paginated = query.paginate(
            page=page, per_page=per_page, error_out=False
        )

        schema = DiagnosisCatalogResponseSchema(many=True)
        data = schema.dump(paginated.items)
        for i, item in enumerate(paginated.items):
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

        return {
            "message": "Catálogo de diagnóstico obtenido correctamente.",
            "diagnosis_catalog": data,
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
        Crea un nuevo registro en el catálogo de diagnóstico.
        """
        schema = DiagnosisCatalogCreateSchema()
        try:
            payload = request.get_json() or {}
            data = schema.load(payload)
        except ValidationError as err:
            return {
                "message": "Error de validación.",
                "errors": err.messages,
            }, 400

        diagnosis = DiagnosisCatalog(
            concept=data["concept"],
            detail=data["detail"],
            description=data.get("description"),
            is_active=True,
            user_id=current_user.id,
        )

        db.session.add(diagnosis)
        db.session.commit()

        resp_schema = DiagnosisCatalogResponseSchema()
        return {
            "message": "Registro de diagnóstico creado correctamente.",
            "diagnosis_catalog": resp_schema.dump(diagnosis),
        }, 201


@api.route("/<int:diagnosis_id>")
class DiagnosisCatalogDetail(Resource):

    @login_required
    @role_required("admin", "manager", "archivist")
    def get(self, diagnosis_id: int):
        """
        Obtiene un registro del catálogo de diagnóstico por ID.
        """
        diagnosis = DiagnosisCatalog.query.get(diagnosis_id)
        if not diagnosis or diagnosis.deleted_at is not None:
            return {
                "message": "Registro de diagnóstico no encontrado."
            }, 404

        schema = DiagnosisCatalogResponseSchema()
        resp = schema.dump(diagnosis)

        resp["user"] = (
            {
                "id": diagnosis.user.id,
                "employee_id": diagnosis.user.employee_id,
                "first_name": diagnosis.user.first_name,
                "last_name": diagnosis.user.last_name,
                "email": diagnosis.user.email,
            }
            if diagnosis.user
            else None
        )
        return {
            "message": "Registro de diagnóstico obtenido correctamente.",
            "diagnosis_catalog": resp,
        }, 200

    @login_required
    @role_required("admin", "manager", "archivist")
    def put(self, diagnosis_id: int):
        """
        Actualiza parcialmente un registro del catálogo de diagnóstico.
        Permite modificar: concept, detail, description, is_active.
        """
        schema = DiagnosisCatalogUpdateSchema()
        try:
            payload = request.get_json() or {}
            payload["id"] = diagnosis_id
            data = schema.load(payload)
        except ValidationError as err:
            return {
                "message": "Error de validación.",
                "errors": err.messages,
            }, 400

        diagnosis = DiagnosisCatalog.query.get(diagnosis_id)
        if not diagnosis or diagnosis.deleted_at is not None:
            return {
                "message": "Registro de diagnóstico no encontrado."
            }, 404

        if "concept" in data:
            diagnosis.concept = data["concept"]
        if "detail" in data:
            diagnosis.detail = data["detail"]
        if "description" in data:
            diagnosis.description = data["description"]
        if "is_active" in data:
            diagnosis.is_active = data["is_active"]

        try:
            diagnosis.updated_at = db.func.now()
            diagnosis.user_id=current_user.id,
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            return {
                "message": "Error al guardar en base de datos.",
                "error": str(e),
            }, 500

        schema = DiagnosisCatalogResponseSchema()
        return {
            "message": "Registro de diagnóstico actualizado correctamente.",
            "diagnosis_catalog": schema.dump(diagnosis),
        }, 200

    @login_required
    @role_required("admin", "manager", "archivist")
    def delete(self, diagnosis_id: int):
        """
        Borrado lógico del registro del catálogo de diagnóstico.
        """
        diagnosis = DiagnosisCatalog.query.get(diagnosis_id)
        if not diagnosis or diagnosis.deleted_at is not None:
            return {
                "message": "Registro de diagnóstico no encontrado."
            }, 404

        diagnosis.deleted_at = db.func.now()
        diagnosis.is_active = False

        db.session.commit()

        return {
            "message": "Registro de diagnóstico eliminado correctamente."
        }, 200
