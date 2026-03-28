from docx import Document
from django.conf import settings
import os
from datetime import datetime


def generate_platform_note(request_obj) -> str:
    """Generate a platform note (note plateforme) DOCX for a request."""
    template_path = os.path.join(settings.DATA_DIR, 'templates', 'note_plateforme_template.docx')
    if os.path.exists(template_path):
        doc = Document(template_path)
    else:
        doc = Document()
        doc.add_heading('Note de Plateforme — PLAGENOR', level=1)
        doc.add_heading('ESSBO — École Supérieure en Sciences Biologiques d\'Oran', level=2)

    doc.add_paragraph(f"Référence: {request_obj.display_id}")
    doc.add_paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y')}")
    doc.add_paragraph(f"Service: {request_obj.service.name if request_obj.service else 'N/A'}")
    doc.add_paragraph(f"Canal: {request_obj.channel}")

    if request_obj.requester:
        doc.add_paragraph(f"Demandeur: {request_obj.requester.get_full_name()}")
        doc.add_paragraph(f"Organisation: {request_obj.requester.organization}")

    doc.add_paragraph(f"Budget estimé: {request_obj.budget_amount} DZD")
    doc.add_paragraph(f"Urgence: {request_obj.urgency}")

    out_dir = os.path.join(settings.MEDIA_ROOT, 'documents')
    os.makedirs(out_dir, exist_ok=True)
    filename = f"NOTE_{request_obj.display_id}_{datetime.now().strftime('%Y%m%d')}.docx"
    filepath = os.path.join(out_dir, filename)
    doc.save(filepath)
    return filepath


def generate_sample_reception_sheet(request_obj, appointment_date='') -> str:
    """Generate sample reception DOCX."""
    doc = Document()
    doc.add_heading('Fiche de Réception d\'Échantillons', level=1)
    doc.add_heading('PLAGENOR — ESSBO', level=2)

    table = doc.add_table(rows=8, cols=2)
    table.style = 'Light Grid Accent 1'
    fields = [
        ("Référence", request_obj.display_id),
        ("Service", request_obj.service.code if request_obj.service else ''),
        ("Demandeur", request_obj.requester.get_full_name() if request_obj.requester else request_obj.guest_name),
        ("Canal", request_obj.channel),
        ("Date RDV", str(appointment_date or request_obj.appointment_date or '')),
        ("Urgence", request_obj.urgency),
        ("Date de réception", "___/___/______"),
        ("Observations", ""),
    ]
    for i, (label, value) in enumerate(fields):
        table.rows[i].cells[0].text = label
        table.rows[i].cells[1].text = str(value)

    doc.add_paragraph("\n")
    doc.add_paragraph("Signature du réceptionniste: ________________")
    doc.add_paragraph("Signature du déposant: ________________")

    out_dir = os.path.join(settings.MEDIA_ROOT, 'documents')
    os.makedirs(out_dir, exist_ok=True)
    filename = f"RECEPTION_{request_obj.display_id}.docx"
    filepath = os.path.join(out_dir, filename)
    doc.save(filepath)
    return filepath


def generate_invoice_document(invoice_obj) -> str:
    """Generate invoice DOCX."""
    doc = Document()
    doc.add_heading(f'Facture {invoice_obj.invoice_number}', level=1)
    doc.add_heading('GENOCLAB — ESSBO', level=2)

    doc.add_paragraph(f"Date: {invoice_obj.created_at.strftime('%d/%m/%Y')}")
    if invoice_obj.client:
        doc.add_paragraph(f"Client: {invoice_obj.client.get_full_name()}")

    doc.add_paragraph(f"Sous-total HT: {invoice_obj.subtotal_ht} DZD")
    doc.add_paragraph(f"TVA ({invoice_obj.vat_rate * 100:.0f}%): {invoice_obj.vat_amount} DZD")
    doc.add_paragraph(f"Total TTC: {invoice_obj.total_ttc} DZD")

    out_dir = os.path.join(settings.MEDIA_ROOT, 'documents')
    os.makedirs(out_dir, exist_ok=True)
    filename = f"INVOICE_{invoice_obj.invoice_number}.docx"
    filepath = os.path.join(out_dir, filename)
    doc.save(filepath)
    return filepath
