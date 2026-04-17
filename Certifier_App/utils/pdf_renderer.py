# In-memory binary stream (used to build PDF before saving)
from io import BytesIO

# Used for formatting date fields
from datetime import date, datetime

# Used to save generated PDF to model
from django.core.files.base import ContentFile

# Color utilities for PDF text
from reportlab.lib import colors

# Default page size
from reportlab.lib.pagesizes import letter

# Converts image file → PDF-readable object
from reportlab.lib.utils import ImageReader

# Core PDF drawing tool
from reportlab.pdfgen import canvas

# For landscape orientation
from reportlab.lib.pagesizes import landscape


def _clamp_pct(value, default=50.0):
     # Ensures percentage values (xPct, yPct) stay within 0–100
    try:
        pct = float(value)
    except (TypeError, ValueError):
        pct = float(default)
    return max(0.0, min(100.0, pct))


def _parse_font_size(value, default=24):
    # Ensures font size is within reasonable range
    try:
        size = float(value)
    except (TypeError, ValueError):
        size = float(default)
    return max(8.0, min(200.0, size))


def _parse_color(value):
    # Converts hex string (e.g. "#000000") → ReportLab color
    if isinstance(value, str) and value.strip():
        try:
            return colors.HexColor(value.strip())
        except ValueError:
            return colors.black
    return colors.black


def _certificate_field_value(cert, key):
    # Formats certificate fields dynamically based on marker "key"
    date_value = cert.date_issued

    # Normalize date into string format
    if isinstance(date_value, datetime):
        formatted_date = date_value.date().isoformat()
    elif isinstance(date_value, date):
        formatted_date = date_value.isoformat()
    elif date_value is None:
        formatted_date = ''
    else:
        formatted_date = str(date_value)

    # Map marker keys → actual certificate fields
    mapping = {
        'full_name': cert.full_name,
        'course': cert.course,
        'issued_by': cert.issued_by,
        'date_issued': formatted_date,
        'title': cert.title,
        'certificate_id': cert.certificate_id,
    }
    # Return empty if key not found
    return str(mapping.get(key, ''))


def _draw_default_layout(pdf, cert):
    # Fallback layout if no markers are defined
    pdf.setFont('Helvetica', 14)
    pdf.setFillColor(colors.black)
    pdf.drawString(100, 750, f"Certificate ID: {cert.certificate_id}")
    pdf.drawString(100, 720, f"Name: {cert.full_name}")
    pdf.drawString(100, 690, f"Course: {cert.course}")
    pdf.drawString(100, 660, f"Issued By: {cert.issued_by}")
    pdf.drawString(100, 630, f"Date: {cert.date_issued}")


def _load_background_reader(template):
    # Loads background image from template for use in PDF
    if not (template and template.background and template.background.name):
        return None, None, None

    try:
        # Get actual file path
        image_path = template.background.path  # IMPORTANT

        # Convert to ReportLab-compatible object
        reader = ImageReader(image_path)

        # Get image dimensions
        width, height = reader.getSize()

        return reader, width, height

    except Exception as e:
        print("BACKGROUND LOAD ERROR:", e)
        return None, None, None

def build_certificate_pdf_bytes(cert):
    # Get linked template
    template = cert.template

    # Placeholder positions
    markers = []

    # Background image object
    background_reader = None

    # Default page size
    page_width, page_height = letter

    # Load background image
    bg_reader, bg_width, bg_height = _load_background_reader(template)
    if bg_reader is not None and bg_width and bg_height:
        background_reader = bg_reader

        # Auto-adjust orientation (landscape if width > height)
        if bg_width > bg_height:
            page_width, page_height = landscape((bg_width, bg_height))
        else:
            page_width, page_height = bg_width, bg_height
    else:
        page_width, page_height = letter  # fallback safety

        # Load placeholder markers from template JSON
    if template and isinstance(template.placeholders, dict):
        raw_markers = template.placeholders.get('markers', [])
        if isinstance(raw_markers, list):
            markers = raw_markers

    # Create PDF in memory
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(page_width, page_height))

    # Draw background image (if available)
    if background_reader is not None:
        pdf.drawImage(
            background_reader,
            0,
            0,
            width=page_width,
            height=page_height,
            preserveAspectRatio=False,
            mask='auto',
        )

    # Track if any text is drawn
    rendered_marker = False

    # Loop through all markers (dynamic positioning)
    for marker in markers:
        if not isinstance(marker, dict):
            continue

        key = marker.get('key')
        value = _certificate_field_value(cert, key)
        if not value:
            continue
        
         # Convert percentage → actual coordinates
        x_pct = _clamp_pct(marker.get('xPct'), default=50.0)
        y_pct = _clamp_pct(marker.get('yPct'), default=50.0)

         # Style settings
        x = (x_pct / 100.0) * page_width
        y = page_height - ((y_pct / 100.0) * page_height)

        font_size = _parse_font_size(marker.get('fontSize'), default=24)
        align = str(marker.get('align', 'left')).lower()

        pdf.setFont('Helvetica', font_size)
        pdf.setFillColor(_parse_color(marker.get('color')))

        # Draw text with alignment
        if align == 'center':
            pdf.drawCentredString(x, y, value)
        elif align == 'right':
            pdf.drawRightString(x, y, value)
        else:
            pdf.drawString(x, y, value)

        rendered_marker = True

    # If no markers rendered → fallback layout
    if not rendered_marker:
        _draw_default_layout(pdf, cert)

     # Finalize PDF
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    # Return PDF as bytes
    return buffer.getvalue()


def generate_and_attach_certificate_pdf(cert):
     # Generate PDF bytes
    pdf_bytes = build_certificate_pdf_bytes(cert)
    # Save PDF to model file field
    cert.file.save(
        f"{cert.certificate_id}.pdf",
        ContentFile(pdf_bytes),
        save=True,
    )
    # Return saved file reference
    return cert.file