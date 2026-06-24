# In-memory binary stream (used to build PDF before saving)
from io import BytesIO
from urllib.parse import urljoin

# Used for formatting date fields
from datetime import date, datetime

# Used to save generated PDF to model
from django.core.files.base import ContentFile
from django.conf import settings
from django.urls import reverse

# Color utilities for PDF text
from reportlab.lib import colors

# Default page size
from reportlab.lib.pagesizes import letter

# Converts image file → PDF-readable object
from reportlab.lib.utils import ImageReader

# Core PDF drawing tool
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# For landscape orientation
from reportlab.lib.pagesizes import landscape
from reportlab.graphics.barcode import qr as qr_lib
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF


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


def _parse_positive_size(value, default=120.0):
    try:
        size = float(value)
    except (TypeError, ValueError):
        size = float(default)
    return max(24.0, min(500.0, size))


def _parse_positive_pct(value, default=10.0):
    try:
        pct = float(value)
    except (TypeError, ValueError):
        pct = float(default)
    return max(1.0, min(100.0, pct))


def _parse_color(value):
    # Converts hex string (e.g. "#000000") → ReportLab color
    if isinstance(value, str) and value.strip():
        try:
            return colors.HexColor(value.strip())
        except ValueError:
            return colors.black
    return colors.black


# Font registration cache
_REGISTERED_FONTS = set()
_FAILED_FONT_FILES = set()


def _register_project_fonts():
    """Register available font files from project `static/fonts` or similar locations.

    Searches these locations in order:
      - settings.FONT_DIR (if present)
      - <BASE_DIR>/static/fonts
      - app static fonts folder (Certifier_App/static/fonts)

    Registers TTF/OTF files with ReportLab using the filename (without ext)
    as the font name (e.g. 'Poppins-Bold').
    """
    global _REGISTERED_FONTS

    paths = []
    try:
        font_dir = getattr(settings, 'FONT_DIR', '') or ''
        if font_dir:
            paths.append(font_dir)
    except Exception:
        pass

    try:
        base_dir = getattr(settings, 'BASE_DIR', '') or ''
        if base_dir:
            paths.append(os.path.join(base_dir, 'static', 'fonts'))
    except Exception:
        pass

    # app-local static fonts
    app_fonts = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'static', 'fonts'))
    paths.append(app_fonts)

    tried = set()
    for p in paths:
        if not p or p in tried:
            continue
        tried.add(p)
        if not os.path.isdir(p):
            continue
        try:
            for fname in os.listdir(p):
                fpath = os.path.join(p, fname)
                if not os.path.isfile(fpath):
                    continue
                lower = fname.lower()
                if not (lower.endswith('.ttf') or lower.endswith('.otf')):
                    # ReportLab TTFont does not register woff/woff2.
                    continue

                name = os.path.splitext(fname)[0]
                if name in _REGISTERED_FONTS:
                    # Already registered in-process.
                    continue
                try:
                    pdfmetrics.registerFont(TTFont(name, fpath))
                    _REGISTERED_FONTS.add(name)
                except Exception as exc:
                    # If registration fails for this file, keep going.
                    # Log once in DEBUG mode to aid troubleshooting.
                    if fpath not in _FAILED_FONT_FILES:
                        _FAILED_FONT_FILES.add(fpath)
                        if bool(getattr(settings, 'DEBUG', False)):
                            print(f"FONT REGISTER ERROR: {fpath} -> {exc}")
                    continue
        except Exception:
            continue


def _resolve_font_name(font_family, font_style, font_weight):
    """Map requested font properties to a registered font name.

    Examples:
      ('Poppins', 'normal', 'bold') -> 'Poppins-Bold' if registered
      ('Poppins', 'italic', 'bold') -> 'Poppins-BoldItalic' if registered
    Falls back to None if no matching registered font is found.
    """
    _register_project_fonts()

    if not font_family:
        return None

    fam = str(font_family).strip()
    # Frontend may send CSS fallback stacks like "Poppins, sans-serif".
    # ReportLab only knows the real family name, so keep the first token.
    if ',' in fam:
        fam = fam.split(',', 1)[0].strip()
    fam = fam.strip('"').strip("'")
    style = (str(font_style or 'normal') or 'normal').lower()
    weight = (str(font_weight or 'normal') or 'normal').lower()

    # Normalize weight values (support numeric strings)
    if weight.isdigit():
        weight_num = int(weight)
        if weight_num >= 700:
            weight = 'bold'
        else:
            weight = 'normal'

    candidates = []
    seen_candidates = set()

    def add_candidate(name):
        if name and name not in seen_candidates:
            seen_candidates.add(name)
            candidates.append(name)

    # Preferred naming: Family-BoldItalic, Family-Bold, Family-Italic, Family-Regular
    name_bases = [fam]
    compact_base = fam.replace(' ', '')
    if compact_base != fam:
        name_bases.append(compact_base)

    for name_base in name_bases:
        if weight == 'bold' and style in ('italic', 'oblique'):
            add_candidate(f"{name_base}-BoldItalic")
            add_candidate(f"{name_base}BoldItalic")
        if weight == 'bold':
            add_candidate(f"{name_base}-Bold")
            add_candidate(f"{name_base}Bold")
        if style in ('italic', 'oblique'):
            add_candidate(f"{name_base}-Italic")
            add_candidate(f"{name_base}Italic")
        # regular/default
        add_candidate(f"{name_base}-Regular")
        add_candidate(name_base)

    for cand in candidates:
        if cand in _REGISTERED_FONTS:
            return cand

    # Last-pass relaxed matching for filenames like Magnolia_Script or
    # magnoliascript that don't exactly match frontend family naming.
    compact = ''.join(ch for ch in fam.lower() if ch.isalnum())
    if compact:
        for registered in _REGISTERED_FONTS:
            reg_compact = ''.join(ch for ch in registered.lower() if ch.isalnum())
            if reg_compact.startswith(compact):
                # Favor style/weight-compatible variants when possible.
                r = registered.lower().replace('-', '').replace('_', '')
                wants_bold = weight == 'bold'
                wants_italic = style in ('italic', 'oblique')
                has_bold = 'bold' in r
                has_italic = 'italic' in r or 'oblique' in r
                if wants_bold == has_bold and wants_italic == has_italic:
                    return registered

        # If no exact style/weight match, return any family match.
        for registered in _REGISTERED_FONTS:
            reg_compact = ''.join(ch for ch in registered.lower() if ch.isalnum())
            if reg_compact.startswith(compact):
                return registered

    return None


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


def _build_qr_payload(cert):
    encode_mode = str(getattr(settings, 'QR_ENCODE_MODE', 'certificate_id') or 'certificate_id').strip().lower()

    if encode_mode == 'verification_url':
        verify_path = reverse('verify_certificate', kwargs={'certificate_id': cert.certificate_id})
        base_url = str(getattr(settings, 'VERIFICATION_BASE_URL', '') or '').strip()
        if not base_url:
            return verify_path

        if not base_url.endswith('/'):
            base_url = f"{base_url}/"
        return urljoin(base_url, verify_path.lstrip('/'))

    return cert.certificate_id


def _draw_qr_from_marker(pdf, marker, page_width, page_height, verify_url):
    x_pct = _clamp_pct(marker.get('xPct'), default=90.0)
    y_pct = _clamp_pct(marker.get('yPct'), default=88.0)

    width_pct = marker.get('widthPct')
    height_pct = marker.get('heightPct')
    size_pct = marker.get('sizePct')
    size_px = marker.get('size')

    if width_pct is not None and height_pct is not None:
        qr_width = (_parse_positive_pct(width_pct, default=12.0) / 100.0) * page_width
        qr_height = (_parse_positive_pct(height_pct, default=12.0) / 100.0) * page_height
    elif size_pct is not None:
        size_from_pct = (_parse_positive_pct(size_pct, default=16.0) / 100.0) * min(page_width, page_height)
        qr_width = size_from_pct
        qr_height = size_from_pct
    else:
        size = _parse_positive_size(size_px, default=min(page_width, page_height) * 0.16)
        qr_width = size
        qr_height = size

    x = (x_pct / 100.0) * page_width
    y = page_height - ((y_pct / 100.0) * page_height)

    qr_width = _parse_positive_size(qr_width)
    qr_height = _parse_positive_size(qr_height)

    widget = qr_lib.QrCodeWidget(verify_url)
    qr_color = _parse_color(marker.get('color'))
    
    # Detect if the color is too light (which makes it unscannable on white templates
    # and also unreadable as inverted QR on dark templates by most phone cameras)
    color_val = str(marker.get('color') or '').strip().lower()
    is_light_color = color_val in ('white', 'yellow', 'lightgray', 'lightgrey', 'cyan', '#fff', '#ffffff')
    
    if not is_light_color and color_val.startswith('#'):
        color_hex = color_val.lstrip('#')
        if len(color_hex) in (3, 6):
            try:
                if len(color_hex) == 3:
                    r = int(color_hex[0] * 2, 16)
                    g = int(color_hex[1] * 2, 16)
                    b = int(color_hex[2] * 2, 16)
                else:
                    r = int(color_hex[0:2], 16)
                    g = int(color_hex[2:4], 16)
                    b = int(color_hex[4:6], 16)
                luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
                if luminance > 0.75:
                    is_light_color = True
            except ValueError:
                pass

    if is_light_color:
        # Force the modules to be black for high contrast scannability
        qr_color = colors.black

    try:
        widget.barFillColor = qr_color
        widget.barStrokeColor = qr_color
    except Exception:
        pass
    bounds = widget.getBounds()
    x1, y1, x2, y2 = bounds
    drawing = Drawing(qr_width, qr_height, transform=[
        qr_width / (x2 - x1),
        0,
        0,
        qr_height / (y2 - y1),
        -x1 * qr_width / (x2 - x1),
        -y1 * qr_height / (y2 - y1),
    ])
    drawing.add(widget)

    # Marker anchor defaults to center to match common drag marker UIs.
    # Supported anchors: center, top-left, bottom-left.
    anchor = str(marker.get('anchor') or 'center').strip().lower()
    if anchor in ('top-left', 'top_left', 'topleft'):
        draw_x = x
        draw_y = y - qr_height
    elif anchor in ('bottom-left', 'bottom_left', 'bottomleft'):
        draw_x = x
        draw_y = y
    else:
        draw_x = x - (qr_width / 2.0)
        draw_y = y - (qr_height / 2.0)

    # If the color is too light, draw a solid white background square 
    # as a quiet zone to ensure standard dark-on-light scannability
    if is_light_color:
        pdf.saveState()
        pdf.setFillColor(colors.white)
        padding = 4  # 4 points padding for quiet zone
        pdf.rect(draw_x - padding, draw_y - padding, qr_width + (padding * 2), qr_height + (padding * 2), fill=True, stroke=False)
        pdf.restoreState()

    renderPDF.draw(drawing, pdf, draw_x, draw_y)


def _draw_default_qr(pdf, page_width, page_height, verify_url):
    default_size = min(page_width, page_height) * 0.16
    marker = {
        'xPct': 90.0,
        'yPct': 88.0,
        'size': default_size,
    }
    _draw_qr_from_marker(pdf, marker, page_width, page_height, verify_url)


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
        # Read file into memory buffer to support both local and remote storage
        with template.background.open('rb') as f:
            image_data = BytesIO(f.read())

        # Convert to ReportLab-compatible object
        reader = ImageReader(image_data)

        # Get image dimensions
        width, height = reader.getSize()

        return reader, width, height

    except Exception as e:
        print("BACKGROUND LOAD ERROR:", e)
        return None, None, None

def build_certificate_pdf_bytes(cert, bg_info=None):
    # Get linked template
    template = cert.template

    # Placeholder positions
    markers = []

    # Background image object
    background_reader = None

    # Default page size
    page_width, page_height = letter

    # Load background image or use provided info
    if bg_info:
        bg_reader, bg_width, bg_height = bg_info
    else:
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
    qr_drawn = False
    verify_url = _build_qr_payload(cert)

    # Loop through all markers (dynamic positioning)
    for marker in markers:
        if not isinstance(marker, dict):
            continue

        key = marker.get('key')

        if key == 'qr_code':
            _draw_qr_from_marker(pdf, marker, page_width, page_height, verify_url)
            qr_drawn = True
            continue

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

        # Resolve font from marker settings
        font_family = marker.get('fontFamily')
        font_style = marker.get('fontStyle')
        font_weight = marker.get('fontWeight')

        font_name = None
        try:
            font_name = _resolve_font_name(font_family, font_style, font_weight)
        except Exception:
            font_name = None

        # Apply color
        pdf.setFillColor(_parse_color(marker.get('color')))

        # Set font (fall back to built-in Helvetica variants)
        try:
            if font_name:
                pdf.setFont(font_name, font_size)
            else:
                fw = str(font_weight or '').lower()
                fs = str(font_style or '').lower()
                is_bold = fw == 'bold' or (fw.isdigit() and int(fw) >= 700)
                is_italic = fs in ('italic', 'oblique')

                if is_bold and is_italic:
                    pdf.setFont('Helvetica-BoldOblique', font_size)
                elif is_bold:
                    pdf.setFont('Helvetica-Bold', font_size)
                elif is_italic:
                    pdf.setFont('Helvetica-Oblique', font_size)
                else:
                    pdf.setFont('Helvetica', font_size)
        except Exception:
            pdf.setFont('Helvetica', font_size)

        # Draw text with alignment (positioning unchanged)
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

    if not qr_drawn:
        _draw_default_qr(pdf, page_width, page_height, verify_url)

     # Finalize PDF
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    # Return PDF as bytes
    return buffer.getvalue()


def generate_and_attach_certificate_pdf(cert, bg_info=None):
     # Generate PDF bytes
    pdf_bytes = build_certificate_pdf_bytes(cert, bg_info=bg_info)
    # Save PDF to model file field
    cert.file.save(
        f"{cert.certificate_id}.pdf",
        ContentFile(pdf_bytes),
        save=True,
    )
    # Return saved file reference
    return cert.file