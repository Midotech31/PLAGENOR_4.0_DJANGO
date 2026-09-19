import io
from functools import lru_cache


@lru_cache(maxsize=1)
def valid_pdf_bytes():
    from pypdf import PdfWriter
    target = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(target)
    writer.close()
    return target.getvalue()


@lru_cache(maxsize=1)
def valid_docx_bytes():
    from docx import Document
    target = io.BytesIO()
    document = Document()
    document.add_paragraph('Synthetic document fixture.')
    document.save(target)
    return target.getvalue()
