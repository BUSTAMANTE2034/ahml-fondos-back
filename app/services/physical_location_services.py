from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.graphics.barcode import qr
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing

def build_physical_location_label_pdf(physical_location):
    buffer = BytesIO()

    # =============================
    # MEDIDAS DE LA ETIQUETA
    # =============================
    WIDTH = 10 * cm
    HEIGHT = 4 * cm

    c = canvas.Canvas(buffer, pagesize=(WIDTH, HEIGHT))

    code = physical_location.code

    qr_url = (
        # f"http://localhost:5173/"
        f"http://189.195.96.226/"
        f"fondos/physical_locations/{code}/detail"
    )

    # =============================
    # TEXTO (IZQUIERDA)
    # =============================
    c.setFont("Helvetica-Bold", 18)

    text_x = 1 * cm
    text_y = HEIGHT / 2 - 6

    c.drawString(
        text_x,
        text_y,
        f"{code}"
    )

    # =============================
    # QR (DERECHA)
    # =============================
    qr_widget = qr.QrCodeWidget(qr_url)
    bounds = qr_widget.getBounds()
    qr_width = bounds[2] - bounds[0]
    qr_height = bounds[3] - bounds[1]

    qr_size = 3.2 * cm

    d = Drawing(
        qr_size,
        qr_size,
        transform=[
            qr_size / qr_width,
            0,
            0,
            qr_size / qr_height,
            0,
            0,
        ],
    )
    d.add(qr_widget)

    qr_x = WIDTH - qr_size - 0.8 * cm
    qr_y = (HEIGHT - qr_size) / 2

    renderPDF.draw(d, c, qr_x, qr_y)

    # =============================
    # BORDE (OPCIONAL, PARA IMPRESIÓN)
    # =============================
    c.setLineWidth(1)
    c.rect(0.1 * cm, 0.1 * cm, WIDTH - 0.2 * cm, HEIGHT - 0.2 * cm)

    c.showPage()
    c.save()

    buffer.seek(0)
    return buffer
