# documents/pdf_styles.py — PLAGENOR 4.0 Shared PDF Styles and Helpers
# Contains shared styles, fonts, colors, and helper functions for all PDF generators

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import Image, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.platypus.flowables import Flowable
from django.conf import settings
import os
import logging

logger = logging.getLogger('plagenor.documents')

# =============================================================================
# CONSTANTS
# =============================================================================

# Page dimensions
MARGIN = 2 * cm
PAGE_WIDTH, PAGE_HEIGHT = A4

# Color palette
COLOR_PRIMARY = HexColor('#1a3c5e')  # Dark blue - headers
COLOR_SECONDARY = HexColor('#2d5a87')  # Medium blue
COLOR_ACCENT = HexColor('#4a90c2')  # Light blue - links/highlights
COLOR_BORDER = HexColor('#cccccc')  # Light gray - borders
COLOR_HEADER_BG = HexColor('#f0f4f8')  # Very light blue - table headers
COLOR_ROW_ALT = HexColor('#fafbfc')  # Alternate row background
COLOR_WARNING = HexColor('#e74c3c')  # Red - warnings
COLOR_SUCCESS = HexColor('#27ae60')  # Green - success
COLOR_TEXT = HexColor('#333333')  # Dark gray - body text
COLOR_GRAY = HexColor('#666666')  # Medium gray - secondary text
COLOR_LIGHT_GRAY = HexColor('#999999')  # Light gray - footnotes

# Fonts (using standard fonts that work with reportlab)
FONT_HELVETICA = 'Helvetica'
FONT_HELVETICA_BOLD = 'Helvetica-Bold'
FONT_TIMES = 'Times-Roman'
FONT_TIMES_BOLD = 'Times-Bold'
FONT_COURIER = 'Courier'
FONT_COURIER_BOLD = 'Courier-Bold'

# =============================================================================
# LOGO HELPERS
# =============================================================================

def get_logo(name, width=3*cm):
    """
    Load logo from static/images/ directory.
    
    Args:
        name: Filename of the logo (e.g., 'essbo_logo.png', 'plagenor_logo.png')
        width: Desired width of the logo (height auto-calculated)
        
    Returns:
        reportlab.platypus.Image or None if file not found
    """
    try:
        # Try multiple possible static directory locations
        static_dirs = getattr(settings, 'STATICFILES_DIRS', [])
        static_root = getattr(settings, 'STATIC_ROOT', None)
        
        possible_paths = []
        
        if static_root:
            possible_paths.append(os.path.join(static_root, 'images', name))
        
        for static_dir in static_dirs:
            possible_paths.append(os.path.join(static_dir, 'images', name))
        
        # Also try MEDIA_ROOT for uploaded logos
        media_root = getattr(settings, 'MEDIA_ROOT', None)
        if media_root:
            possible_paths.append(os.path.join(media_root, 'images', name))
            possible_paths.append(os.path.join(media_root, 'logos', name))
        
        for path in possible_paths:
            if os.path.exists(path):
                # Calculate height maintaining aspect ratio (assuming ~0.6 aspect ratio)
                height = width * 0.6
                return Image(path, width=width, height=height)
        
        logger.debug(f"Logo not found: {name}")
        return None
        
    except Exception as e:
        logger.warning(f"Error loading logo {name}: {e}")
        return None


def get_essbo_logo(width=3*cm):
    """Get ESSBO logo. Alias for get_logo with common filename."""
    return get_logo('essbo_logo.png', width) or get_logo('logo_essbo.png', width)


def get_plagenor_logo(width=3*cm):
    """Get PLAGENOR logo. Alias for get_logo with common filename."""
    return get_logo('plagenor_logo.png', width) or get_logo('logo_plagenor.png', width)


# =============================================================================
# STYLE FACTORY
# =============================================================================

def get_styles():
    """
    Get the complete stylesheet with all PLAGENOR custom styles.
    
    Returns:
        StyleSheetWithOverrides with custom styles added
    """
    styles = getSampleStyleSheet()
    
    # -------------------------------------------------------------------------
    # Document-level styles
    # -------------------------------------------------------------------------
    styles.add(ParagraphStyle(
        name='DocumentTitle',
        fontName=FONT_TIMES_BOLD,
        fontSize=18,
        textColor=COLOR_PRIMARY,
        alignment=TA_CENTER,
        spaceAfter=12,
        spaceBefore=6,
    ))
    
    styles.add(ParagraphStyle(
        name='DocumentSubtitle',
        fontName=FONT_TIMES,
        fontSize=12,
        textColor=COLOR_SECONDARY,
        alignment=TA_CENTER,
        spaceAfter=6,
    ))
    
    styles.add(ParagraphStyle(
        name='Reference',
        fontName=FONT_COURIER,
        fontSize=9,
        textColor=COLOR_GRAY,
        alignment=TA_RIGHT,
        spaceAfter=4,
    ))
    
    # -------------------------------------------------------------------------
    # Section styles
    # -------------------------------------------------------------------------
    styles.add(ParagraphStyle(
        name='SectionTitle',
        fontName=FONT_TIMES_BOLD,
        fontSize=12,
        textColor=COLOR_PRIMARY,
        spaceBefore=12,
        spaceAfter=6,
        borderColor=COLOR_BORDER,
        borderWidth=0,
        borderPadding=0,
    ))
    
    styles.add(ParagraphStyle(
        name='SectionTitleWithLine',
        fontName=FONT_TIMES_BOLD,
        fontSize=12,
        textColor=COLOR_PRIMARY,
        spaceBefore=12,
        spaceAfter=6,
    ))
    
    styles.add(ParagraphStyle(
        name='SubsectionTitle',
        fontName=FONT_TIMES_BOLD,
        fontSize=10,
        textColor=COLOR_SECONDARY,
        spaceBefore=8,
        spaceAfter=4,
    ))
    
    # -------------------------------------------------------------------------
    # Body text styles
    # -------------------------------------------------------------------------
    styles.add(ParagraphStyle(
        name='BodySerif',
        fontName=FONT_TIMES,
        fontSize=10,
        leading=14,
        textColor=COLOR_TEXT,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    ))
    
    styles.add(ParagraphStyle(
        name='BodySans',
        fontName=FONT_HELVETICA,
        fontSize=9,
        leading=12,
        textColor=COLOR_TEXT,
        alignment=TA_LEFT,
        spaceAfter=4,
    ))
    
    styles.add(ParagraphStyle(
        name='BodySmall',
        fontName=FONT_HELVETICA,
        fontSize=8,
        leading=10,
        textColor=COLOR_GRAY,
        alignment=TA_LEFT,
    ))
    
    # -------------------------------------------------------------------------
    # Table styles
    # -------------------------------------------------------------------------
    styles.add(ParagraphStyle(
        name='TableHeader',
        fontName=FONT_HELVETICA_BOLD,
        fontSize=9,
        textColor=COLOR_PRIMARY,
        alignment=TA_CENTER,
    ))
    
    styles.add(ParagraphStyle(
        name='TableCell',
        fontName=FONT_HELVETICA,
        fontSize=9,
        textColor=COLOR_TEXT,
        alignment=TA_LEFT,
        leading=11,
    ))
    
    styles.add(ParagraphStyle(
        name='TableCellCenter',
        fontName=FONT_HELVETICA,
        fontSize=9,
        textColor=COLOR_TEXT,
        alignment=TA_CENTER,
    ))
    
    # -------------------------------------------------------------------------
    # Label/Value styles
    # -------------------------------------------------------------------------
    styles.add(ParagraphStyle(
        name='Label',
        fontName=FONT_HELVETICA_BOLD,
        fontSize=9,
        textColor=COLOR_GRAY,
        alignment=TA_LEFT,
    ))
    
    styles.add(ParagraphStyle(
        name='Value',
        fontName=FONT_HELVETICA,
        fontSize=10,
        textColor=COLOR_TEXT,
        alignment=TA_LEFT,
    ))
    
    # -------------------------------------------------------------------------
    # Special styles
    # -------------------------------------------------------------------------
    styles.add(ParagraphStyle(
        name='WarningBox',
        fontName=FONT_HELVETICA_BOLD,
        fontSize=10,
        textColor=COLOR_WARNING,
        alignment=TA_LEFT,
        spaceBefore=8,
        spaceAfter=8,
        leftIndent=6,
    ))
    
    styles.add(ParagraphStyle(
        name='CenterBold',
        fontName=FONT_TIMES_BOLD,
        fontSize=14,
        textColor=COLOR_PRIMARY,
        alignment=TA_CENTER,
        spaceAfter=6,
    ))
    
    styles.add(ParagraphStyle(
        name='Center',
        fontName=FONT_TIMES,
        fontSize=11,
        textColor=COLOR_TEXT,
        alignment=TA_CENTER,
        spaceAfter=4,
    ))
    
    styles.add(ParagraphStyle(
        name='SmallItalic',
        fontName=FONT_HELVETICA + '-Oblique',
        fontSize=8,
        textColor=COLOR_LIGHT_GRAY,
        alignment=TA_LEFT,
    ))
    
    styles.add(ParagraphStyle(
        name='Footer',
        fontName=FONT_HELVETICA,
        fontSize=8,
        textColor=COLOR_LIGHT_GRAY,
        alignment=TA_CENTER,
    ))
    
    styles.add(ParagraphStyle(
        name='Signature',
        fontName=FONT_TIMES,
        fontSize=9,
        textColor=COLOR_TEXT,
        alignment=TA_LEFT,
    ))
    
    styles.add(ParagraphStyle(
        name='SignatureLabel',
        fontName=FONT_HELVETICA,
        fontSize=8,
        textColor=COLOR_GRAY,
        alignment=TA_LEFT,
    ))
    
    styles.add(ParagraphStyle(
        name='ChecklistItem',
        fontName=FONT_HELVETICA,
        fontSize=9,
        textColor=COLOR_TEXT,
        alignment=TA_LEFT,
        leftIndent=12,
        spaceAfter=2,
    ))
    
    styles.add(ParagraphStyle(
        name='ImportantNote',
        fontName=FONT_HELVETICA_BOLD,
        fontSize=10,
        textColor=COLOR_PRIMARY,
        alignment=TA_LEFT,
        spaceBefore=8,
        spaceAfter=4,
    ))
    
    return styles


# =============================================================================
# TABLE STYLE HELPERS
# =============================================================================

def get_base_table_style(header_count=0, alternating=True):
    """
    Get a base TableStyle for PLAGENOR tables.
    
    Args:
        header_count: Number of header rows (will be styled differently)
        alternating: Whether to use alternating row colors
        
    Returns:
        TableStyle with base styling applied
    """
    style_commands = [
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('BOX', (0, 0), (-1, -1), 1, COLOR_PRIMARY),
        
        # Alignment
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]
    
    # Style header rows
    if header_count > 0:
        style_commands.extend([
            ('BACKGROUND', (0, 0), (-1, header_count - 1), COLOR_HEADER_BG),
            ('FONTNAME', (0, 0), (-1, header_count - 1), FONT_HELVETICA_BOLD),
            ('TEXTCOLOR', (0, 0), (-1, header_count - 1), COLOR_PRIMARY),
            ('ALIGN', (0, 0), (-1, header_count - 1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, header_count - 1), 'MIDDLE'),
        ])
    
    # Alternating row colors
    if alternating:
        start_row = header_count if header_count > 0 else 0
        for i in range(start_row, 100):  # Max 100 rows
            if i % 2 == 0:
                bg_color = COLOR_ROW_ALT
            else:
                bg_color = white
            style_commands.append(
                ('BACKGROUND', (0, i), (-1, i), bg_color)
            )
    
    return TableStyle(style_commands)


def style_label_value_table(table, col_widths=None):
    """
    Apply standard styling to a label/value table.
    
    Args:
        table: The table to style
        col_widths: Optional column widths [label_width, value_width]
    """
    style_commands = [
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('BOX', (0, 0), (-1, -1), 1, COLOR_PRIMARY),
        
        # Label column styling
        ('FONTNAME', (0, 0), (0, -1), FONT_HELVETICA_BOLD),
        ('TEXTCOLOR', (0, 0), (0, -1), COLOR_GRAY),
        ('BACKGROUND', (0, 0), (0, -1), COLOR_HEADER_BG),
        
        # Value column styling
        ('FONTNAME', (1, 0), (1, -1), FONT_HELVETICA),
        ('TEXTCOLOR', (1, 0), (1, -1), COLOR_TEXT),
        
        # Alignment
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        
        # Padding
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]
    
    table.setStyle(TableStyle(style_commands))
    
    if col_widths:
        table._argW = col_widths


# =============================================================================
# LAYOUT HELPERS
# =============================================================================

class HorizontalLine(Flowable):
    """A simple horizontal line flowable."""
    
    def __init__(self, width, thickness=0.5, color=COLOR_BORDER):
        Flowable.__init__(self)
        self.line_width = width
        self.thickness = thickness
        self.color = color
        self.height = thickness + 2
    
    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 0, self.line_width, 0)


class SectionDivider(Flowable):
    """A section divider with optional label."""
    
    def __init__(self, width, label=None, color=COLOR_PRIMARY):
        Flowable.__init__(self)
        self.line_width = width
        self.label = label
        self.color = color
        self.height = 16 if label else 12
    
    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(1)
        self.canv.line(0, 6, self.line_width, 6)
        if self.label:
            self.canv.setFont(FONT_HELVETICA_BOLD, 9)
            self.canv.setFillColor(self.color)
            self.canv.drawString(0, 0, self.label)


class WarningBox(Flowable):
    """A bordered warning/important box."""
    
    def __init__(self, width, text, icon='⚠', bg_color=HexColor('#fff3cd'), 
                 border_color=HexColor('#ffc107'), text_color=COLOR_PRIMARY):
        Flowable.__init__(self)
        self.box_width = width
        self.text = text
        self.icon = icon
        self.bg_color = bg_color
        self.border_color = border_color
        self.text_color = text_color
        self.height = 30  # Will be calculated in wrap
    
    def wrap(self, availableWidth, availableHeight):
        # Simple height estimation
        self.width = min(self.box_width, availableWidth)
        chars_per_line = int(self.width / 5)  # Approximate chars per line
        lines = max(1, len(self.text) // chars_per_line + 1)
        self.height = lines * 14 + 16
        return self.width, self.height
    
    def draw(self):
        from reportlab.pdfbase.pdfmetrics import stringWidth
        
        # Background
        self.canv.setFillColor(self.bg_color)
        self.canv.roundRect(0, 0, self.width, self.height, 4, fill=1, stroke=0)
        
        # Border
        self.canv.setStrokeColor(self.border_color)
        self.canv.setLineWidth(1)
        self.canv.roundRect(0, 0, self.width, self.height, 4, fill=0, stroke=1)
        
        # Icon and text
        self.canv.setFillColor(self.text_color)
        self.canv.setFont(FONT_HELVETICA_BOLD, 12)
        self.canv.drawString(8, self.height - 18, self.icon + ' ' + self.text)


class SignatureBlock(Flowable):
    """A signature block with label and blank line."""
    
    def __init__(self, width, label, date_label='Date:', line_length=100):
        Flowable.__init__(self)
        self.block_width = width
        self.label = label
        self.date_label = date_label
        self.line_length = line_length
        self.height = 60
    
    def wrap(self, availableWidth, availableHeight):
        self.width = min(self.block_width, availableWidth)
        return self.width, self.height
    
    def draw(self):
        # Label
        self.canv.setFont(FONT_HELVETICA, 9)
        self.canv.setFillColor(COLOR_GRAY)
        self.canv.drawString(0, 40, self.label)
        
        # Signature line
        self.canv.setStrokeColor(COLOR_TEXT)
        self.canv.setLineWidth(0.5)
        self.canv.line(0, 25, self.line_length, 25)
        
        # Date label and line
        self.canv.drawString(0, 10, self.date_label)
        self.canv.line(40, 10, 40 + 60, 10)


# =============================================================================
# PAGE TEMPLATE HELPERS
# =============================================================================

def make_page_template(canvas, doc, with_page_numbers=True):
    """
    Standard page template function for use with PageTemplate.
    
    Args:
        canvas: The canvas object
        doc: The document object
        with_page_numbers: Whether to add page numbers
        
    Usage:
        from reportlab.platypus import BaseDocTemplate, PageTemplate
        doc = BaseDocTemplate(...)
        doc.addPageTemplates([PageTemplate(
            id='main',
            frames=frame,
            onPage=lambda c, d: make_page_template(c, d)
        )])
    """
    # Save state
    canvas.saveState()
    
    # Footer
    if with_page_numbers:
        canvas.setFont(FONT_HELVETICA, 8)
        canvas.setFillColor(COLOR_LIGHT_GRAY)
        
        # Footer text (left)
        footer_text = f"PLAGENOR 4.0"
        canvas.drawString(MARGIN, 0.75 * cm, footer_text)
        
        # Page number (right)
        page_num = canvas.getPageNumber()
        canvas.drawRightString(PAGE_WIDTH - MARGIN, 0.75 * cm, f"{page_num}")
        
        # Bottom line
        canvas.setStrokeColor(COLOR_BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 1.1 * cm, PAGE_WIDTH - MARGIN, 1.1 * cm)
    
    # Restore state
    canvas.restoreState()


def make_header_footer(canvas, doc, title='', with_page_numbers=True):
    """
    Extended page template with header on first page.
    
    Args:
        canvas: The canvas object
        doc: The document object
        title: Optional title for header
        with_page_numbers: Whether to add page numbers
    """
    canvas.saveState()
    
    # Header line (only on first page)
    if canvas.getPageNumber() == 1:
        canvas.setStrokeColor(COLOR_PRIMARY)
        canvas.setLineWidth(2)
        canvas.line(MARGIN, PAGE_HEIGHT - 1.5 * cm, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 1.5 * cm)
    
    # Footer
    if with_page_numbers:
        canvas.setFont(FONT_HELVETICA, 8)
        canvas.setFillColor(COLOR_LIGHT_GRAY)
        
        # Footer text
        canvas.drawString(MARGIN, 0.75 * cm, f"PLAGENOR 4.0 — {title}")
        
        # Page number
        page_num = canvas.getPageNumber()
        canvas.drawRightString(PAGE_WIDTH - MARGIN, 0.75 * cm, f"{page_num}")
        
        # Bottom line
        canvas.setStrokeColor(COLOR_BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 1.1 * cm, PAGE_WIDTH - MARGIN, 1.1 * cm)
    
    canvas.restoreState()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def format_date(date_obj, format_str='%d/%m/%Y'):
    """Format a date object to string."""
    if date_obj is None:
        return ''
    if hasattr(date_obj, 'strftime'):
        return date_obj.strftime(format_str)
    return str(date_obj)


def format_datetime(datetime_obj, format_str='%d/%m/%Y à %H:%M'):
    """Format a datetime object to string."""
    if datetime_obj is None:
        return ''
    if hasattr(datetime_obj, 'strftime'):
        return datetime_obj.strftime(format_str)
    return str(datetime_obj)


def format_currency(amount, currency='DZD'):
    """Format a number as currency."""
    if amount is None:
        return 'N/A'
    try:
        return f"{float(amount):,.2f} {currency}"
    except (ValueError, TypeError):
        return str(amount)


def truncate_text(text, max_length=50, suffix='...'):
    """Truncate text to maximum length."""
    if not text:
        return ''
    text = str(text)
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def safe_getattr(obj, attr, default=None):
    """Safely get an attribute from an object."""
    try:
        return getattr(obj, attr, default)
    except Exception:
        return default


def get_sample_style_sheet():
    """Alias for get_styles() for compatibility."""
    return get_styles()
