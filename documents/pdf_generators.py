# documents/pdf_generators.py — PLAGENOR 4.0 PDF Generator Stub
# For IBTIKAR form PDF, this now delegates to pdf_generator_ibtikar.py
# which implements the official template structure

from io import BytesIO
from datetime import datetime
import logging

from django.conf import settings

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus.flowables import Flowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

from .pdf_styles import (
    MARGIN, PAGE_WIDTH, PAGE_HEIGHT,
    COLOR_PRIMARY, COLOR_SECONDARY, COLOR_BORDER, COLOR_HEADER_BG,
    COLOR_TEXT, COLOR_GRAY, COLOR_LIGHT_GRAY, COLOR_WARNING,
    FONT_HELVETICA, FONT_HELVETICA_BOLD, FONT_TIMES, FONT_TIMES_BOLD,
    get_styles, get_base_table_style, style_label_value_table,
    get_essbo_logo, get_plagenor_logo,
    format_date, make_page_template
)
from .pdf_labels import LABELS_FR, LABELS_EN

logger = logging.getLogger('plagenor.documents')


def generate_ibtikar_form_pdf(request_obj, lang='fr', force_regenerate=False):
    """
    Generate an IBTIKAR Analysis Request Form PDF for a request.

    This function now delegates to the official template implementation
    in pdf_generator_ibtikar.py for a professional, official layout.

    Args:
        request_obj: Request model instance
        lang: Language code ('fr' or 'en')
        force_regenerate: If True, regenerate even if already saved

    Returns:
        bytes: PDF file content
    """
    from .pdf_generator_ibtikar import generate_ibtikar_form_pdf as gen_pdf
    
    # Get language from additional_data or service_params if not explicitly provided
    additional_data = request_obj.additional_data or {}
    service_params = request_obj.service_params or {}
    actual_lang = lang or additional_data.get('language') or service_params.get('language', 'fr')
    
    return gen_pdf(request_obj, lang=actual_lang, force_regenerate=force_regenerate)


def check_template_status(request_obj):
    """
    Stub for backward compatibility with stale dashboard imports.
    Returns a minimal status dict for the IBTIKAR form.
    """
    from .pdf_generator_ibtikar import check_ibtikar_form_status
    return check_ibtikar_form_status(request_obj)
