# app/services/record_file_services.py

"""Servicios y funciones de apoyo para la gestión de expedientes documentales."""

from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl import Workbook
from sqlalchemy import case, cast, Integer, func, text
from flask import Request
from sqlalchemy import case
from reportlab.lib.pagesizes import letter
from datetime import datetime
from io import BytesIO
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.styles import getSampleStyleSheet
from sqlalchemy import or_, and_

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen import canvas

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image,
)
from typing import Optional
from reportlab.lib.utils import ImageReader
from app.extensions import db
from app.models.record_file import RecordFile
from app.models.fund import Fund
from app.models.section import Section
from app.models.series import Series
from app.models.location import Location
from app.models.deterioration import Deterioration
from app.models.typology import Typology
from app.models.record_file_typology import RecordFileTypology
from app.models.user import User
from app.schemas.record_file import RecordFileResponseSchema
from reportlab.graphics.barcode import code128
import os
from flask import current_app
from reportlab.platypus import Image, Spacer
from reportlab.lib.units import cm
REPORT_COLOR = colors.Color(115/255.0, 74/255.0, 31/255.0)  # #734A1F


def _validate_active_entity(entity, entity_name: str = "Entidad"):
    """
    Valida que una entidad exista, no esté eliminada y, si tiene is_active, que esté activa.
    Devuelve un string con el error o None si está bien.
    """
    if not entity:
        return f"{entity_name} no encontrada."
    if getattr(entity, "deleted_at", None) is not None:
        return f"{entity_name} está eliminada y no puede usarse."
    if hasattr(entity, "is_active") and entity.is_active is False:
        return f"{entity_name} está inactiva y no puede usarse."
    return None


def _parse_date(date_str: str):

    if not date_str:
        return None

    # Formatos permitidos
    formats = ["%Y-%m-%d", "%d-%m-%Y"]

    for fmt in formats:
        try:
            parsed = datetime.strptime(date_str, fmt).date()
            print(" Fecha parseada con formato", fmt, "→", parsed)
            return parsed
        except ValueError:
            continue

    print(" Ningún formato coincidió")
    return None


def _apply_ordering(query, order_by_param: str):
    # -----------------------------
    # ORDEN LÓGICO POR DISPONIBILIDAD (solo si aplica)
    # -----------------------------
    status_order = case(
        (RecordFile.availability_status == "available", 1),
        (RecordFile.availability_status == "on_loan", 2),
        (RecordFile.availability_status == "under_review", 3),
        (RecordFile.availability_status == "unavailable", 4),
        else_=99,
    )

    # Si no se envió ningún order_by → ordenar solo por status + updated_at desc
    if not order_by_param:
        return query.order_by(status_order, RecordFile.updated_at.desc())

    # ===========================================================
    # LIMPIAR Y EXTRAER NUMEROS DE box_number
    # ===========================================================
    clean_box = func.trim(RecordFile.box_number)
    digits_box = func.regexp_replace(clean_box, r'[^0-9]', '')  # solo números

    box_as_int = func.coalesce(
        cast(func.nullif(digits_box, ""), Integer),
        999999999
    )

    # ===========================================================
    # LIMPIAR Y EXTRAER NUMEROS DE file_number
    # ===========================================================
    clean_file = func.trim(RecordFile.file_number)
    digits_file = func.regexp_replace(clean_file, r'[^0-9]', '')

    file_as_int = func.coalesce(
        cast(func.nullif(digits_file, ""), Integer),
        999999999
    )

    # ===========================================================
    # MAPEO FINAL DE CAMPOS
    # ===========================================================
    mapping = {
        "created_at_asc": RecordFile.created_at.asc(),
        "created_at_desc": RecordFile.created_at.desc(),

        "updated_at_asc": RecordFile.updated_at.asc(),
        "updated_at_desc": RecordFile.updated_at.desc(),

        "file_date_asc": RecordFile.file_date.asc(),
        "file_date_desc": RecordFile.file_date.desc(),

        "deterioration_status_updated_at_asc":
            RecordFile.deterioration_status_updated_at.asc(),
        "deterioration_status_updated_at_desc":
            RecordFile.deterioration_status_updated_at.desc(),

        # Ordenamiento REAL numérico
        "box_number_asc": box_as_int.asc(),
        "box_number_desc": box_as_int.desc(),

        "file_number_asc": file_as_int.asc(),
        "file_number_desc": file_as_int.desc(),
    }

    sort_expr = mapping.get(order_by_param)

    # Si no coincide → usar updated_at por defecto
    if sort_expr is None:
        return query.order_by(status_order, RecordFile.updated_at.desc())

    # ===========================================================
    # 🔥 SI ORDENA POR NÚMEROS → IGNORAR DISPONIBILIDAD
    # ===========================================================
    if order_by_param in [
        "box_number_asc", "box_number_desc",
        "file_number_asc", "file_number_desc",
        # "created_at_asc", "created_at_desc",
        # "updated_at_asc", "updated_at_desc",
        # "file_date_asc", "file_date_desc",
        # "deterioration_status_updated_at_asc", "deterioration_status_updated_at_desc",
    ]:
        return query.order_by(sort_expr)

    # Caso normal → ordenar por disponibilidad primero
    return query.order_by(status_order, sort_expr)


def _build_record_file_query_from_request(req: "Request"):
    """
    Construye un query de `RecordFile` aplicando todos los filtros soportados,
    a partir de los parámetros del request.

    IMPORTANTE: solo se consideran los filtros listados abajo. Ya no se filtra
    por IDs (fund_id, section_id, etc.) ni por usuario.

    Parámetros de consulta soportados (query string):

    Paginación (se manejan en el endpoint, NO aquí):
        - page (int, opcional): número de página (por defecto 1).
        - per_page (int, opcional): tamaño de página (por defecto 20).

    Búsqueda global:
        - query (str, opcional):
            Término de búsqueda libre. Se aplica como coincidencia parcial (ILIKE)
            sobre:
                * reference_code
                * file_number
                * box_number

    Mini-queries por campo:
        - reference_code (str, opcional):
            Coincidencia parcial sobre `RecordFile.reference_code`.

        - file_number (str, opcional):
            Coincidencia parcial sobre `RecordFile.file_number`.

        - box_number (str, opcional):
            Coincidencia parcial sobre `RecordFile.box_number`.

        - fund_name (str, opcional):
            Coincidencia parcial sobre:
                * Fund.name
                * Fund.acronym

        - section_name (str, opcional):
            Coincidencia parcial sobre:
                * Section.name
                * Section.acronym

        - series_name (str, opcional):
            Coincidencia parcial sobre:
                * Series.name
                * Series.acronym

        - location_name (str, opcional):
            Coincidencia parcial sobre Location.name.

        - deterioration_name (str, opcional):
            Coincidencia parcial sobre Deterioration.name.

        - typology_name (str, opcional):
            Coincidencia parcial sobre Typology.name a través de la relación
            `record_file_typologies` (solo tipologías no eliminadas).

    Filtros de confidencialidad:
        - sensitive (str, opcional):
            Estado de confidencialidad. Valores esperados:
                * "all" (por defecto): no aplica filtro.
                * "delicate": solo expedientes con `sensitive_data == True`.
                * "not delicate": solo expedientes con `sensitive_data == False`.
            (Se aceptan también "not_delicate", "true", "false", "1", "0" como
             variantes prácticas.)

    Filtros de disponibilidad:
        - availability_status (str, opcional):
            Estado de disponibilidad. Valores esperados:
                * "all" (por defecto): no aplica filtro.
                * "available"
                * "unavailable"
                * "under_review"
                * "on_loan"

    Filtros por fecha documental:
        - file_date_after (str, opcional):
            Fecha en formato "YYYY-MM-DD". Incluye expedientes cuyo
            `file_date >= file_date_after`.

        - file_date_before (str, opcional):
            Fecha en formato "YYYY-MM-DD". Incluye expedientes cuyo
            `file_date <= file_date_before`.

            Si se envían ambos parámetros, se devuelven los expedientes cuyo
            `file_date` se encuentra dentro del intervalo [after, before].

    Ordenamiento:
        - order_by (str, opcional):
            Campo de ordenamiento. Valores soportados:
                * "created_at_asc" / "created_at_desc"
                * "updated_at_asc" / "updated_at_desc"
                * "file_date_asc" / "file_date_desc"
                * "deterioration_status_updated_at_asc"
                  "deterioration_status_updated_at_desc"

            Siempre se aplica primero el orden lógico por disponibilidad
            (ver `_apply_ordering`) y después este campo.
    """
    # --- Parámetros de texto/libres ---
    query_param = (req.args.get("query", "") or "").strip()

    reference_code_param = (req.args.get("reference_code", "") or "").strip()
    previous_reference_param = (req.args.get(
        "previous_reference_code", "") or "").strip()

    file_number_param = (req.args.get("file_number", "") or "").strip()
    box_number_param = (req.args.get("box_number", "") or "").strip()

    fund_name_param = (req.args.get("fund_name", "") or "").strip()
    section_name_param = (req.args.get("section_name", "") or "").strip()
    series_name_param = (req.args.get("series_name", "") or "").strip()
    location_name_param = (req.args.get("location_name", "") or "").strip()
    deterioration_name_param = (req.args.get(
        "deterioration_name", "") or "").strip()
    typology_name_param = (req.args.get("typology_name", "") or "").strip()

    # --- Filtros de estado / confidencialidad ---
    sensitive_param = (req.args.get("sensitive") or "all").strip().lower()
    availability_param = (req.args.get("availability_status") or "all").strip()

    # --- Rango de fechas (file_date) ---
    file_date_after_param = req.args.get("file_date_after")
    print(" file_date_after recibido:", file_date_after_param)
    file_date_before_param = req.args.get("file_date_before")

    # --- Ordenamiento ---
    order_by_param = req.args.get("order_by")

    # --- Query base: solo expedientes no eliminados ---
    q = RecordFile.query.filter(RecordFile.deleted_at.is_(None))

    # ===============================
    # 1) BÚSQUEDA GLOBAL (query)
    # ===============================
    if query_param:
        like = f"%{query_param}%"
        q = q.filter(
            or_(
                RecordFile.reference_code.ilike(like),
                RecordFile.file_number.ilike(like),
                RecordFile.box_number.ilike(like),
            )
        )

    # ==================================
    # 2) MINI-QUERIES POR CAMPO DIRECTO
    # ==================================
    if reference_code_param:
        like = f"%{reference_code_param}%"
        q = q.filter(RecordFile.reference_code.ilike(like))

    if previous_reference_param:
        like = f"%{previous_reference_param}%"
        q = q.filter(RecordFile.previous_reference_code.ilike(like))

    if file_number_param:
        like = f"%{file_number_param}%"
        q = q.filter(RecordFile.file_number.ilike(like))

    if box_number_param:
        like = f"%{box_number_param}%"
        q = q.filter(RecordFile.box_number.ilike(like))

    # =========================================
    # 3) MINI-QUERIES POR NOMBRE EN RELACIONES
    # =========================================
    if fund_name_param:
        like = f"%{fund_name_param}%"
        q = q.join(Fund, Fund.id == RecordFile.fund_id).filter(
            or_(Fund.name.ilike(like), Fund.acronym.ilike(like))
        )

    if section_name_param:
        like = f"%{section_name_param}%"
        q = q.join(Section, Section.id == RecordFile.section_id).filter(
            or_(Section.name.ilike(like), Section.acronym.ilike(like))
        )

    if series_name_param:
        like = f"%{series_name_param}%"
        q = q.join(Series, Series.id == RecordFile.series_id).filter(
            or_(Series.name.ilike(like), Series.acronym.ilike(like))
        )

    if location_name_param:
        like = f"%{location_name_param}%"
        q = q.join(Location, Location.id == RecordFile.location_id).filter(
            Location.name.ilike(like)
        )

    if deterioration_name_param:
        like = f"%{deterioration_name_param}%"
        q = q.join(
            Deterioration,
            Deterioration.id == RecordFile.deterioration_status_id,
        ).filter(Deterioration.name.ilike(like))

    if typology_name_param:
        like = f"%{typology_name_param}%"
        q = q.join(
            RecordFileTypology,
            and_(
                RecordFileTypology.record_file_id == RecordFile.id,
                RecordFileTypology.deleted_at.is_(None),
            ),
        ).join(
            Typology,
            and_(
                Typology.id == RecordFileTypology.typology_id,
                Typology.deleted_at.is_(None),
            ),
        ).filter(Typology.name.ilike(like))

    # =========================
    # 4) CONFIDENCIALIDAD
    # =========================
    if sensitive_param in {"delicate", "sensitive", "true", "1"}:
        q = q.filter(RecordFile.sensitive_data.is_(True))
    elif sensitive_param in {"not delicate", "not_delicate", "false", "0"}:
        q = q.filter(RecordFile.sensitive_data.is_(False))
    # "all" u otros valores → no se filtra

    # =========================
    # 5) DISPONIBILIDAD
    # =========================
    if availability_param and availability_param != "all":
        q = q.filter(RecordFile.availability_status == availability_param)

    # =========================
    # 6) RANGO DE FECHAS (file_date)
    # =========================
    file_date_after = _parse_date(file_date_after_param)
    file_date_before = _parse_date(file_date_before_param)

    if file_date_after:
        q = q.filter(RecordFile.file_date >= file_date_after)
    if file_date_before:
        q = q.filter(RecordFile.file_date <= file_date_before)

    # =========================
    # 7) ORDENAMIENTO
    # =========================
    q = _apply_ordering(q, order_by_param)

    return q


def _serialize_record_file(obj: RecordFile):
    """
    Serializa el expediente con todas las relaciones anidadas:
    - user
    - fund
    - section
    - series
    - location
    - deterioration_status
    - typologies (solo activas)
    """
    base = RecordFileResponseSchema().dump(obj)

    base["user"] = (
        {
            "id": obj.user.id,
            "first_name": obj.user.first_name,
            "last_name": obj.user.last_name,
            "email": obj.user.email,
        }
        if obj.user
        else None
    )

    base["fund"] = (
        {
            "id": obj.fund.id,
            "name": obj.fund.name,
            "acronym": obj.fund.acronym,
            "start_date": obj.fund.start_date.isoformat() if obj.fund.start_date else None,
            "end_date": obj.fund.end_date.isoformat() if obj.fund.end_date else None,
        }
        if obj.fund
        else None
    )

    base["section"] = (
        {
            "id": obj.section.id,
            "name": obj.section.name,
            "acronym": obj.section.acronym,
            "start_date": obj.section.start_date.isoformat() if obj.section.start_date else None,
            "end_date": obj.section.end_date.isoformat() if obj.section.end_date else None,
        }
        if obj.section
        else None
    )

    base["series"] = (
        {
            "id": obj.series.id,
            "name": obj.series.name,
            "acronym": obj.series.acronym,
            "start_date": obj.series.start_date.isoformat() if obj.series.start_date else None,
            "end_date": obj.series.end_date.isoformat() if obj.series.end_date else None,
        }
        if obj.series
        else None
    )

    base["location"] = (
        {
            "id": obj.location.id,
            "name": obj.location.name,
        }
        if obj.location
        else None
    )

    base["deterioration_status"] = (
        {
            "id": obj.deterioration_status.id,
            "name": obj.deterioration_status.name,
            "description": obj.deterioration_status.description,
            "updated_at": obj.deterioration_status_updated_at.isoformat()
            if obj.deterioration_status_updated_at
            else None,
        }
        if obj.deterioration_status
        else None
    )

    base["typologies"] = [
        {
            "id": rel.typology.id,
            "name": rel.typology.name,
            "description": rel.typology.description,
        }
        for rel in obj.record_file_typologies
        if rel.deleted_at is None
        and rel.typology
        and rel.typology.deleted_at is None
    ]

    return base


def _build_record_files_pdf(record_files):
    """
    Construye un PDF con la tabla de expedientes y devuelve un buffer en memoria.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    elements = []
    styles = getSampleStyleSheet()

    title = Paragraph("Reporte de expedientes", styles["Heading2"])
    elements.append(title)
    elements.append(Spacer(1, 12))

    # encabezados de la tabla
    data = [
        ["ID", "Código", "Asunto", "Fondo", "Sección",
            "Ubicación", "Estado", "Fecha doc."]
    ]

    for rf in record_files:
        data.append([
            rf.id,
            rf.reference_code or "",
            rf.subject or "",
            rf.fund.name if rf.fund else "",
            rf.section.name if rf.section else "",
            rf.location.name if rf.location else "",
            rf.availability_status or "",
            rf.file_date.isoformat() if rf.file_date else "",
        ])

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), REPORT_COLOR),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, REPORT_COLOR),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


def _build_reference_code(fund=None, section=None, serie=None,
                          box_number=None, file_number=None):
    """
    FUND-SECCION-SERIE-C.{box_number}-Exp.{file_number}
    usando acrónimos si existen.
    """
    parts = []
    if fund:
        parts.append(fund.acronym or fund.name)
    if section:
        parts.append(section.acronym or section.name)
    if serie:
        parts.append(serie.acronym or serie.name)

    code = "-".join(parts)

    if box_number:
        code += f"-C.{box_number}"
    if file_number:
        code += f"-Exp.{file_number}"

    return code


def _exists_record_file_with_number_global(file_number, exclude_id=None):
    """
    Devuelve True si ya existe un expediente (no eliminado) con ese file_number.
    """
    if not file_number:
        return False

    q = RecordFile.query.filter(
        RecordFile.deleted_at.is_(None),
        RecordFile.file_number == file_number,
    )
    if exclude_id is not None:
        q = q.filter(RecordFile.id != exclude_id)

    return db.session.query(q.exists()).scalar()


def _sync_record_file_typologies(record_file, typology_ids):
    """
    Sincroniza las tipologías de un expediente con la lista de IDs recibida.
    Marca como deleted_at las que se quitan y crea las nuevas.
    """
    # normalizar a ints
    normalized_ids = []
    for tid in typology_ids or []:
        try:
            normalized_ids.append(int(tid))
        except (TypeError, ValueError):
            continue

    normalized_ids = set(normalized_ids)

    # relaciones existentes
    existing = {
        rel.typology_id: rel for rel in record_file.record_file_typologies}

    # marcar como eliminadas las que ya no están
    for tid, rel in existing.items():
        if tid not in normalized_ids and rel.deleted_at is None:
            rel.deleted_at = db.func.now()

    # agregar o reactivar las que sí están
    for tid in normalized_ids:
        rel = existing.get(tid)
        if rel:
            # reactivar si estaba eliminada
            if rel.deleted_at is not None:
                rel.deleted_at = None
        else:
            db.session.add(
                RecordFileTypology(
                    record_file_id=record_file.id,
                    typology_id=tid,
                )
            )


def _image_path(filename: str) -> Optional[str]:
    base_path = current_app.root_path
    img_path = os.path.join(base_path, "img", filename)
    return img_path if os.path.exists(img_path) else None


def _load_logo(filename: str, width=3 * cm, height=3 * cm):
    path = _image_path(filename)
    if path:
        try:
            return Image(path, width=width, height=height)
        except Exception:
            pass
    return Spacer(width, height)


def _draw_watermark(canvas, doc):
    path = _image_path("escudo.png")
    if not path:
        return

    canvas.saveState()
    try:
        canvas.setFillAlpha(0.05)
    except AttributeError:
        pass

    img = ImageReader(path)
    iw, ih = img.getSize()

    desired_w = 12 * cm  # bien grande
    scale = desired_w / float(iw)
    w = desired_w
    h = ih * scale

    page_w, page_h = doc.pagesize
    x = (page_w - w) / 2.0
    y = (page_h - h) / 2.0

    canvas.drawImage(img, x, y, width=w, height=h, mask="auto")
    canvas.restoreState()


def _field_box(label: str, value: str, width=5 * cm, height=0.9 * cm):
    """
    Devuelve un solo recuadro (una columna) con el texto:
    'Label: valor', tal como en la plantilla.
    """
    text = f"{label} {value or ''}"

    data = [[text]]
    t = Table(
        data,
        colWidths=[width],
        rowHeights=[height],
    )
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.8, colors.black),  # solo borde externo
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )

    return t


def split_text_in_two_lines(c, text, width, font="Helvetica", font_size=9):
    words = text.split()
    line1 = ""

    # Construir línea 1
    for i, word in enumerate(words):
        test = (line1 + " " + word).strip()
        if c.stringWidth(test, font, font_size) <= width:
            line1 = test
        else:
            break
    else:
        # todo cabe en una línea
        return line1, ""

    # Lo que sobra para línea 2
    line2 = " ".join(words[len(line1.split()):])
    return line1, line2


def split_two_lines(c, items, width, font="Helvetica", font_size=9):
    """
    items = lista de bloques ["Oficio,", "Informe técnico,", "Solicitud"]
    """
    line1 = []
    current = ""

    for item in items:
        test = (current + " " + item).strip()
        if c.stringWidth(test, font, font_size) <= width:
            line1.append(item)
            current = test
        else:
            break

    # Lo que sobra → línea 2
    remaining = items[len(line1):]

    return line1, remaining


def draw_single_smart_line(c, text_items, x, y, width, font="Helvetica", font_size=9):
    """
    text_items = lista de palabras/bloques (["Oficio,", "Informe técnico,", "Solicitud"])
    """
    c.setFont(font, font_size)

    if len(text_items) <= 2:
        # NO justificar si hay pocas 'palabras'
        c.drawString(x, y, " ".join(text_items))
        return

    # --- JUSTIFICAR ---
    total_word_width = sum(c.stringWidth(w, font, font_size)
                           for w in text_items)
    space_needed = width - total_word_width
    gaps = len(text_items) - 1
    space_between = space_needed / gaps

    cur_x = x
    for w in text_items:
        c.drawString(cur_x, y, w)
        cur_x += c.stringWidth(w, font, font_size) + space_between


def draw_two_custom_lines(c, text, x1, y1, x2, y2, width, font="Helvetica", font_size=9):
    items = smart_split(text)

    line1, line2 = split_two_lines(c, items, width, font, font_size)

    if line1:
        draw_single_smart_line(c, line1, x1, y1, width, font, font_size)

    if line2:
        draw_single_smart_line(c, line2, x2, y2, width, font, font_size)


def draw_justified_text(c, text, x, y, width, line_height):
    words = text.split()
    line_words = []
    current_width = 0

    for word in words:
        w = c.stringWidth(word + " ", "Helvetica", 10)
        if current_width + w < width:
            line_words.append(word)
            current_width += w
        else:
            if len(line_words) == 1:
                c.drawString(x, y, line_words[0])
            else:
                total_text_width = sum(c.stringWidth(
                    w + " ", "Helvetica", 10) for w in line_words)
                extra_space = width - total_text_width
                space_between = extra_space / (len(line_words) - 1)

                cur_x = x
                for w in line_words:
                    c.drawString(cur_x, y, w)
                    cur_x += c.stringWidth(w + " ",
                                           "Helvetica", 10) + space_between

            y -= line_height
            line_words = [word]
            current_width = c.stringWidth(word + " ", "Helvetica", 10)

    # última línea no justificada
    last_line = " ".join(line_words)
    c.drawString(x, y, last_line)


def normalize_typologies(text):
    # Reemplaza "palabra,palabra" por "palabra, palabra"
    return text.replace(",", ", ")


def smart_split(text):
    """
    Separa usando coma como separador de 'bloques',
    NO separa por espacios dentro del bloque.
    """
    parts = [p.strip() for p in text.split(",")]

    # Añadir las comas pegadas excepto al último
    items = []
    for i, p in enumerate(parts):
        if i < len(parts) - 1:
            items.append(p + ",")
        else:
            items.append(p)
    return items

def parse_previous_reference_code(ref: str):
    """
    Espera un código con formato:
    FONDO-SECCION-SERIE-C.X-Exp.Y
    """
    if not ref:
        return "", "", "", "", ""

    parts = ref.split("-")

    if len(parts) < 5:
        # formato incorrecto
        return "", "", "", "", ""

    fondo = parts[0]
    seccion = parts[1]
    serie = parts[2]
    box_raw = parts[3]
    box = box_raw.replace("C.", "").replace("c.", "").strip()              # ejemplo: C.5

    # Exp.1293 → extraer solo "1293"
    exp_raw = parts[4]
    if exp_raw.lower().startswith("exp."):
        exp = exp_raw[4:]       # quitar "Exp."
    else:
        exp = exp_raw

    return fondo, seccion, serie, box, exp



def build_cover_page(record_file):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    page_w, page_h = letter

    # -------------------------------
    # Fondo plantilla
    # -------------------------------
    bg_path = os.path.join(current_app.root_path, "img",
                           "caratula_template.png")
    if os.path.exists(bg_path):
        bg = ImageReader(bg_path)
        c.drawImage(bg, 0, 0, width=page_w, height=page_h)

    c.setFont("Helvetica", 10)

    # -------------------------------
    # Datos
    fondo_txt = record_file.fund.acronym if record_file.fund else ""
    seccion_txt = record_file.section.acronym if record_file.section else ""
    serie_txt = record_file.series.acronym if record_file.series else ""
    exp_txt = record_file.file_number or ""
    fecha_txt = record_file.file_date.isoformat() if record_file.file_date else ""
    hojas_txt = str(
        record_file.page_count) if record_file.page_count is not None else ""
    localidad_txt = record_file.location.name if record_file.location else ""
    asunto_txt = record_file.subject or ""
    caja_txt = record_file.box_number or ""

    tipo_doc_txt = ",".join(
        rel.typology.name
        for rel in record_file.record_file_typologies
        if rel.deleted_at is None
        and rel.typology
        and rel.typology.deleted_at is None
    )
    size_txt = record_file.document_sizes or ""
    folio_txt = f"{record_file.id:06d}"
    prev_code = record_file.previous_reference_code

    fondo_txt2, seccion_txt2, serie_txt2, box_txt2, exp_txt2 = parse_previous_reference_code(prev_code)

    # -------------------------------
    # POSICIONES
    # -------------------------------
    c.drawString(43 * mm, 235.5 * mm, fondo_txt)
    c.drawString(95 * mm, 235.5 * mm, seccion_txt)
    c.drawString(137 * mm, 235.5 * mm, serie_txt)

    c.drawString(36 * mm, 219.5 * mm, exp_txt)
    c.setFont("Helvetica", 9)
    # c.drawString(120 * mm, 219.5 * mm, tipo_doc_txt)
    draw_two_custom_lines(
        c,
        tipo_doc_txt,
        x1=120 * mm,     # primera línea EXACTAMENTE donde la tenías
        y1=219.5 * mm,
        x2=71.5 * mm,     # segunda línea debajo o en donde tú quieras
        y2=215 * mm,     # AJUSTA ESTO A TU TEMPLATE
        width=44 * mm,
        font="Helvetica",
        font_size=9
    )

    c.setFont("Helvetica", 10)

    c.drawString(40 * mm, 204 * mm, hojas_txt)
    c.drawString(129 * mm, 204 * mm, size_txt)

    c.drawString(50 * mm, 189 * mm, localidad_txt)
    c.drawString(142 * mm, 189 * mm, fecha_txt)

    # -------------------------------
    # ASUNTO MULTILÍNEA (RESUELTO)
    # -------------------------------
    max_width = 170 * mm
    start_x = 26 * mm
    start_y = 168 * mm  # posición EXACTA del cuadro
    line_height = 14

    draw_justified_text(
        c,
        asunto_txt,
        x=start_x,
        y=start_y,
        width=max_width,
        line_height=line_height
    )
 # # Referencia anterior
    c.drawString(110 * mm, 64.5 * mm, fondo_txt2)      # Fondo ref. anterior
    c.drawString(170 * mm, 64.5 * mm, seccion_txt2)    # Sección ref. anterior
    c.drawString(39 * mm, 48.5 * mm, exp_txt2)        # Exp ref. anterior
    c.drawString(106 * mm, 48.5 * mm, serie_txt2)
    # c.setFont("Helvetica", 14)  # Serie ref. anterior
    c.drawString(160 * mm, 48.5 * mm, box_txt2)      # Caja ref. anterior
    # -----------------------------
    # Código de barras
    # -----------------------------
    c.setFont("Helvetica", 8)
    from reportlab.graphics.barcode import code128
    barcode_value = record_file.reference_code or f"EXP-{record_file.id}"
    barcode = code128.Code128(barcode_value, barHeight=15 * mm, barWidth=0.4)
    barcode.drawOn(c, 17 * mm, 15 * mm)
    c.drawString(24 * mm, 12 * mm, barcode_value)

    # -----------------------------
    # Folio
    # -----------------------------
    c.setFont("Helvetica", 10)
    c.drawString(166 * mm, 19.5 * mm, folio_txt)

    # Final
    c.showPage()
    c.save()

    buffer.seek(0)
    return buffer


def timestamp_es():
    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]

    now = datetime.now()

    dia = now.day
    mes = meses[now.month - 1]
    anio = now.year

    hora = now.strftime("%I")
    minuto = now.strftime("%M")
    ampm = "am" if now.strftime("%p") == "AM" else "pm"

    # NOMBRE SEGURO (sin dos puntos ni caracteres prohibidos)
    return f"{dia}-{mes}-{anio} {hora}_{minuto}-{ampm}"


def map_availability(status: str) -> str:
    mapping = {
        "available": "Disponible",
        "on_loan": "En préstamo",
        "under_review": "En revisión",
        "unavailable": "No disponible",
    }
    return mapping.get(status, "Desconocido")


def map_sensitive(value: bool) -> str:
    if value is True:
        return "Dato sensible"
    if value is False:
        return "Normal"
    return "No definido"


def combine_acronym_name(obj):
    """
    Devuelve:
        <catalog_key.key> - <name>
    Ejemplo:
        AM - Alcaldía Mayor
    """
    if not obj:
        return ""

    # Clave del catálogo (el campo correcto es 'key')
    key_value = None
    if hasattr(obj, "catalog_key") and obj.catalog_key:
        key_value = getattr(obj.catalog_key, "key", None)

    # nombre del fondo / sección / serie
    name = obj.name or ""

    # Si hay clave → "AM - Alcaldía Mayor"
    if key_value:
        return f"{key_value} - {name}"

    # Si no hay → solo nombre
    return name


def _build_record_file_query_for_export(req):
    query = RecordFile.query.filter(RecordFile.deleted_at.is_(None))

    # -----------------------------
    # DISPONIBILIDAD
    # -----------------------------
    availability = req.args.get("availability_status")
    if availability and availability != "all":
        query = query.filter(RecordFile.availability_status == availability)

    # -----------------------------
    # FECHAS DOCUMENTALES
    # -----------------------------
    file_after = _parse_date(req.args.get("file_date_after"))
    file_before = _parse_date(req.args.get("file_date_before"))

    if file_after:
        query = query.filter(RecordFile.file_date >= file_after)
    if file_before:
        query = query.filter(RecordFile.file_date <= file_before)

    # -----------------------------
    # FECHA DE CREACIÓN
    # -----------------------------
    created_after = _parse_date(req.args.get("created_after"))
    created_before = _parse_date(req.args.get("created_before"))

    if created_after:
        query = query.filter(RecordFile.created_at >= created_after)
    if created_before:
        query = query.filter(RecordFile.created_at <= created_before)

    # -----------------------------
    # FECHA DE ACTUALIZACIÓN
    # -----------------------------
    updated_after = _parse_date(req.args.get("updated_after"))
    updated_before = _parse_date(req.args.get("updated_before"))

    if updated_after:
        query = query.filter(RecordFile.updated_at >= updated_after)
    if updated_before:
        query = query.filter(RecordFile.updated_at <= updated_before)

    # -----------------------------
    # FECHA DE DETERIORO
    # -----------------------------
    det_after = _parse_date(req.args.get("det_after"))
    det_before = _parse_date(req.args.get("det_before"))

    if det_after:
        query = query.filter(
            RecordFile.deterioration_status_updated_at >= det_after)
    if det_before:
        query = query.filter(
            RecordFile.deterioration_status_updated_at <= det_before)

    # -----------------------------
    # FECHA DE PRESERVACIÓN
    # -----------------------------
    pres_after = _parse_date(req.args.get("preservation_after"))
    pres_before = _parse_date(req.args.get("preservation_before"))

    if pres_after:
        query = query.filter(RecordFile.last_preservation_date >= pres_after)
    if pres_before:
        query = query.filter(RecordFile.last_preservation_date <= pres_before)

    # -----------------------------
    # FECHA DE FONDO
    # -----------------------------
    fund_after = _parse_date(req.args.get("fund_after"))
    fund_before = _parse_date(req.args.get("fund_before"))

    if fund_after:
        query = query.filter(RecordFile.last_fund_date >= fund_after)
    if fund_before:
        query = query.filter(RecordFile.last_fund_date <= fund_before)

    # ORDEN POR DEFECTO
    query = query.order_by(RecordFile.updated_at.desc())

    return query


def _build_record_files_excel(record_files):
    """
    Genera un archivo Excel con los expedientes recibidos.
    Devuelve un BytesIO listo para descargar.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Expedientes"

    headers = [
        "ID",
        "Código",
        "Código anterior",
        "Asunto",
        "Fondo",
        "Sección",
        "Serie",
        "Ubicación",
        "Disponibilidad",
        "Dato sensible",
        "Fecha documental",
        "Fecha creación",
        "Última actualización",
        "Última act. deterioro",
        "Número de páginas",
        "Comentarios",
        "Tipologías",
        "Tamaños de documentos",
        "Usuario creador",
        "Última vez en fondo",
        "Última vez preservación",
    ]

    ws.append(headers)

    # Estilos de encabezado
    header_fill = PatternFill(start_color="DDDDDD",
                              end_color="DDDDDD", fill_type="solid")
    bold_font = Font(bold=True)

    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = bold_font
        col_letter = get_column_letter(col)
        ws.column_dimensions[col_letter].width = 22

    # Contenido
    for rf in record_files:
        ws.append([
            rf.id,
            rf.reference_code or "",
            rf.previous_reference_code or "",
            rf.subject or "",
            combine_acronym_name(rf.fund),
            combine_acronym_name(rf.section),
            combine_acronym_name(rf.series),
            rf.location.name if rf.location else "",
            map_availability(rf.availability_status),
            map_sensitive(rf.sensitive_data),

            rf.file_date.isoformat() if rf.file_date else "",
            rf.created_at.isoformat() if rf.created_at else "",
            rf.updated_at.isoformat() if rf.updated_at else "",
            rf.deterioration_status_updated_at.isoformat(
            ) if rf.deterioration_status_updated_at else "",

            rf.page_count or "",
            
            rf.comments or "",

            ", ".join(
                rel.typology.name
                for rel in rf.record_file_typologies
                if rel.deleted_at is None and rel.typology and rel.typology.deleted_at is None
            ),
            rf.document_sizes or "",

            f"{rf.user.first_name} {rf.user.last_name}" if rf.user else "",

            rf.last_fund_date.isoformat() if hasattr(
                rf, "last_fund_date") and rf.last_fund_date else "",
            rf.last_preservation_date.isoformat() if hasattr(
                rf, "last_preservation_date") and rf.last_preservation_date else "",
        ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
