# documents/__init__.py — PLAGENOR 4.0 Documents Module

# PDF Generators
from .pdf_generator_ibtikar import (
    generate_ibtikar_form_pdf,
    check_ibtikar_form_status,
    delete_ibtikar_form,
)

from .pdf_generator_platform_note import (
    generate_platform_note_pdf,
    check_platform_note_status,
    delete_platform_note,
)

from .pdf_generator_reception import (
    generate_reception_form_pdf,
    check_reception_form_status,
    delete_reception_form,
)

# Labels and styles
from .pdf_labels import get_labels, get_label, LABELS_FR, LABELS_EN
from .pdf_styles import get_styles, get_styles as get_pdf_styles
