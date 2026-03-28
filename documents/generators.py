from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from django.conf import settings
import os
from datetime import datetime


def generate_ibtikar_form(request_obj) -> str:
    """Generate an IBTIKAR form DOCX for a request by cloning a template."""
    template_path = os.path.join(
        settings.BASE_DIR, 'documents', 'docx_templates', 'ibtikar_form_template.docx'
    )
    if os.path.exists(template_path):
        doc = Document(template_path)
    else:
        doc = Document()
        doc.add_heading('Formulaire IBTIKAR — PLAGENOR', level=1)
        doc.add_heading("ESSBO — École Supérieure en Sciences Biologiques d'Oran", level=2)

    # Replace placeholders in existing paragraphs
    replacements = {
        '{{FULL_NAME}}': request_obj.requester.get_full_name() if request_obj.requester else request_obj.guest_name,
        '{{ETABLISSEMENT}}': getattr(request_obj.requester, 'organization', '') if request_obj.requester else '',
        '{{LABORATORY}}': getattr(request_obj.requester, 'laboratory', '') if request_obj.requester else '',
        '{{PROJECT_TITLE}}': request_obj.title,
        '{{SERVICE_NAME}}': request_obj.service.name if request_obj.service else 'N/A',
        '{{DATE}}': datetime.now().strftime('%d/%m/%Y'),
        '{{DISPLAY_ID}}': request_obj.display_id,
        '{{BUDGET_AMOUNT}}': f"{request_obj.budget_amount} DZD",
        '{{URGENCY}}': request_obj.urgency,
    }

    for paragraph in doc.paragraphs:
        for key, value in replacements.items():
            if key in paragraph.text:
                paragraph.text = paragraph.text.replace(key, str(value))

    # Also replace in tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for key, value in replacements.items():
                    if key in cell.text:
                        cell.text = cell.text.replace(key, str(value))

    # If template was not found, add content manually
    if not os.path.exists(template_path):
        doc.add_paragraph(f"Référence: {request_obj.display_id}")
        doc.add_paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y')}")
        doc.add_paragraph('')

        requester_name = request_obj.requester.get_full_name() if request_obj.requester else request_obj.guest_name
        requester_org = getattr(request_obj.requester, 'organization', '') if request_obj.requester else ''
        requester_lab = getattr(request_obj.requester, 'laboratory', '') if request_obj.requester else ''

        table = doc.add_table(rows=8, cols=2)
        table.style = 'Light Grid Accent 1'
        fields = [
            ("Nom complet", requester_name),
            ("Établissement", requester_org),
            ("Laboratoire", requester_lab),
            ("Titre du projet", request_obj.title),
            ("Service demandé", request_obj.service.name if request_obj.service else 'N/A'),
            ("Budget estimé", f"{request_obj.budget_amount} DZD"),
            ("Urgence", request_obj.urgency),
            ("Description", request_obj.description[:200] if request_obj.description else ''),
        ]
        for i, (label, value) in enumerate(fields):
            table.rows[i].cells[0].text = label
            table.rows[i].cells[1].text = str(value)

        # Add sample data table if available
        sample_data = request_obj.sample_table or []
        if sample_data and isinstance(sample_data, list) and len(sample_data) > 0:
            doc.add_paragraph('')
            doc.add_heading('Données des échantillons', level=3)
            if isinstance(sample_data[0], dict):
                headers = list(sample_data[0].keys())
                sample_table = doc.add_table(rows=len(sample_data) + 1, cols=len(headers))
                sample_table.style = 'Light Grid Accent 1'
                for j, h in enumerate(headers):
                    sample_table.rows[0].cells[j].text = str(h)
                for i, row_data in enumerate(sample_data):
                    for j, h in enumerate(headers):
                        sample_table.rows[i + 1].cells[j].text = str(row_data.get(h, ''))

    out_dir = os.path.join(settings.MEDIA_ROOT, 'documents')
    os.makedirs(out_dir, exist_ok=True)
    filename = f"IBTIKAR_{request_obj.display_id}_{datetime.now().strftime('%Y%m%d')}.docx"
    filepath = os.path.join(out_dir, filename)
    doc.save(filepath)
    return filepath


def generate_platform_note(request_obj) -> str:
    """Generate a Platform Note dynamically populated from specific request data."""
    template_path = os.path.join(
        settings.BASE_DIR, 'documents', 'docx_templates', 'platform_note_template.docx'
    )

    if os.path.exists(template_path):
        doc = Document(template_path)
        # Replace placeholders in existing template
        replacements = {
            '{{DISPLAY_ID}}': request_obj.display_id,
            '{{DATE}}': datetime.now().strftime('%d/%m/%Y'),
            '{{FULL_NAME}}': request_obj.requester.get_full_name() if request_obj.requester else request_obj.guest_name or 'N/A',
            '{{ETABLISSEMENT}}': getattr(request_obj.requester, 'organization', '') if request_obj.requester else '',
            '{{LABORATORY}}': getattr(request_obj.requester, 'laboratory', '') if request_obj.requester else '',
            '{{SUPERVISOR}}': getattr(request_obj.requester, 'supervisor', '') if request_obj.requester else '',
            '{{STUDENT_LEVEL}}': getattr(request_obj.requester, 'student_level', '') if request_obj.requester else '',
            '{{SERVICE_CODE}}': request_obj.service.code if request_obj.service else 'N/A',
            '{{SERVICE_NAME}}': request_obj.service.name if request_obj.service else 'N/A',
            '{{SERVICE_DESCRIPTION}}': request_obj.service.description if request_obj.service else '',
            '{{TURNAROUND}}': str(request_obj.service.turnaround_days) if request_obj.service else 'N/A',
            '{{BUDGET_AMOUNT}}': f"{request_obj.budget_amount:,.0f} DZD",
            '{{URGENCY}}': request_obj.urgency,
            '{{CHANNEL}}': request_obj.channel,
            '{{TITLE}}': request_obj.title,
            '{{DESCRIPTION}}': request_obj.description or '',
        }
        for paragraph in doc.paragraphs:
            for key, value in replacements.items():
                if key in paragraph.text:
                    paragraph.text = paragraph.text.replace(key, str(value or ''))
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for key, value in replacements.items():
                        if key in cell.text:
                            cell.text = cell.text.replace(key, str(value or ''))
    else:
        # Build document programmatically with FULL request data
        doc = Document()

        # Header
        doc.add_heading('NOTE DE PLATEFORME — PLAGENOR', level=1)
        doc.add_paragraph("ESSBO — École Supérieure en Sciences Biologiques d'Oran")
        doc.add_paragraph(f"Référence: {request_obj.display_id}")
        doc.add_paragraph(f"Date d'émission: {datetime.now().strftime('%d/%m/%Y à %H:%M')}")
        doc.add_paragraph('')

        # Requester section
        doc.add_heading('Informations du demandeur', level=2)
        requester_name = request_obj.requester.get_full_name() if request_obj.requester else request_obj.guest_name or 'N/A'
        table = doc.add_table(rows=6, cols=2)
        table.style = 'Light Grid Accent 1'
        fields = [
            ('Nom et prénom', requester_name),
            ('Établissement', getattr(request_obj.requester, 'organization', '') if request_obj.requester else ''),
            ('Laboratoire', getattr(request_obj.requester, 'laboratory', '') if request_obj.requester else ''),
            ('Niveau', getattr(request_obj.requester, 'student_level', '') if request_obj.requester else ''),
            ('Directeur de recherche', getattr(request_obj.requester, 'supervisor', '') if request_obj.requester else ''),
            ('Email / Téléphone', f"{getattr(request_obj.requester, 'email', '')} / {getattr(request_obj.requester, 'phone', '')}" if request_obj.requester else request_obj.guest_email or ''),
        ]
        for i, (label, value) in enumerate(fields):
            table.rows[i].cells[0].text = label
            table.rows[i].cells[1].text = str(value or '')

        # Service section
        doc.add_heading('Service demandé', level=2)
        if request_obj.service:
            doc.add_paragraph(f"Code: {request_obj.service.code}")
            doc.add_paragraph(f"Intitulé: {request_obj.service.name}")
            doc.add_paragraph(f"Description: {request_obj.service.description}")
            doc.add_paragraph(f"Délai estimé: {request_obj.service.turnaround_days} jours ouvrables")

        # Request details
        doc.add_heading('Détails de la demande', level=2)
        doc.add_paragraph(f"Titre: {request_obj.title}")
        if request_obj.description:
            doc.add_paragraph(f"Description: {request_obj.description}")
        doc.add_paragraph(f"Canal: {request_obj.channel}")
        doc.add_paragraph(f"Urgence: {request_obj.urgency}")

        # Service parameters (from YAML-driven form)
        if request_obj.service_params:
            doc.add_heading('Paramètres du service', level=3)
            for key, value in request_obj.service_params.items():
                clean_key = key.replace('param_', '').replace('_', ' ').title()
                doc.add_paragraph(f"{clean_key}: {value}")

        # Sample table
        if request_obj.sample_table:
            doc.add_heading('Tableau des échantillons', level=3)
            samples = request_obj.sample_table
            if isinstance(samples, list) and samples:
                if isinstance(samples[0], dict):
                    headers = list(samples[0].keys())
                    t = doc.add_table(rows=len(samples) + 1, cols=len(headers))
                    t.style = 'Light Grid Accent 1'
                    for j, h in enumerate(headers):
                        t.rows[0].cells[j].text = h.replace('_', ' ').title()
                    for i, sample in enumerate(samples):
                        for j, h in enumerate(headers):
                            t.rows[i + 1].cells[j].text = str(sample.get(h, ''))

        # Budget section (IBTIKAR)
        doc.add_heading('Décompte budgétaire IBTIKAR', level=2)
        doc.add_paragraph(f"Budget annuel par étudiant: 200 000 DZD")
        doc.add_paragraph(f"Montant de cette prestation: {request_obj.budget_amount:,.0f} DZD")
        if request_obj.declared_ibtikar_balance:
            doc.add_paragraph(f"Solde IBTIKAR déclaré: {request_obj.declared_ibtikar_balance:,.0f} DZD")

        # Assignment info (if assigned)
        if request_obj.assigned_to:
            doc.add_heading('Assignation', level=2)
            doc.add_paragraph(f"Analyste assigné: {request_obj.assigned_to.user.get_full_name()}")
            if request_obj.appointment_date:
                doc.add_paragraph(f"Date de rendez-vous: {request_obj.appointment_date.strftime('%d/%m/%Y')}")

        # Footer
        doc.add_paragraph('')
        doc.add_paragraph('—' * 40)
        doc.add_paragraph('Ce document est généré automatiquement par PLAGENOR 4.0')
        doc.add_paragraph("ESSBO — Université d'Oran — Prof. Mohamed Merzoug")

    # Save
    os.makedirs(os.path.join(settings.BASE_DIR, 'media', 'documents'), exist_ok=True)
    filename = f"NOTE_PLT_{request_obj.display_id}_{datetime.now().strftime('%Y%m%d')}.docx"
    filepath = os.path.join(settings.BASE_DIR, 'media', 'documents', filename)
    doc.save(filepath)
    return filepath


def generate_quote(request_obj) -> str:
    """Generate a GENOCLAB quote DOCX."""
    from core.models import Invoice
    doc = Document()
    doc.add_heading('Devis — GENOCLAB', level=1)
    doc.add_heading("ESSBO — École Supérieure en Sciences Biologiques d'Oran", level=2)

    # Sequential quote number
    quote_count = Invoice.objects.count() + 1
    quote_number = f"GENOCLAB-DEV-{datetime.now().year}-{quote_count:04d}"

    doc.add_paragraph(f"N° Devis: {quote_number}")
    doc.add_paragraph(f"Référence demande: {request_obj.display_id}")
    doc.add_paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y')}")
    doc.add_paragraph('')

    # Client info
    doc.add_heading('Informations client', level=3)
    if request_obj.requester:
        doc.add_paragraph(f"Client: {request_obj.requester.get_full_name()}")
        doc.add_paragraph(f"Organisation: {request_obj.requester.organization}")
        doc.add_paragraph(f"Email: {request_obj.requester.email}")
    elif request_obj.guest_name:
        doc.add_paragraph(f"Client: {request_obj.guest_name}")
        doc.add_paragraph(f"Email: {request_obj.guest_email}")

    # Service details + line items
    doc.add_heading('Prestations', level=3)
    table = doc.add_table(rows=2, cols=4)
    table.style = 'Light Grid Accent 1'
    headers = ['Description', 'Quantité', 'Prix unitaire', 'Total']
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = h

    service_name = request_obj.service.name if request_obj.service else request_obj.title
    amount = float(request_obj.quote_amount or 0)
    table.rows[1].cells[0].text = service_name
    table.rows[1].cells[1].text = '1'
    table.rows[1].cells[2].text = f"{amount:,.2f} DA"
    table.rows[1].cells[3].text = f"{amount:,.2f} DA"

    doc.add_paragraph('')
    vat_rate = float(settings.VAT_RATE)
    vat_amount = round(amount * vat_rate, 2)
    total_ttc = round(amount + vat_amount, 2)

    summary_table = doc.add_table(rows=3, cols=2)
    summary_table.rows[0].cells[0].text = 'Sous-total HT'
    summary_table.rows[0].cells[1].text = f"{amount:,.2f} DA"
    summary_table.rows[1].cells[0].text = f'TVA ({vat_rate * 100:.0f}%)'
    summary_table.rows[1].cells[1].text = f"{vat_amount:,.2f} DA"
    summary_table.rows[2].cells[0].text = 'Total TTC'
    summary_table.rows[2].cells[1].text = f"{total_ttc:,.2f} DA"

    out_dir = os.path.join(settings.MEDIA_ROOT, 'documents')
    os.makedirs(out_dir, exist_ok=True)
    filename = f"DEVIS_{request_obj.display_id}_{datetime.now().strftime('%Y%m%d')}.docx"
    filepath = os.path.join(out_dir, filename)
    doc.save(filepath)
    return filepath


def generate_reception_form(request_obj) -> str:
    """Generate sample reception form DOCX."""
    doc = Document()
    doc.add_heading("Fiche de Réception d'Échantillons", level=1)
    doc.add_heading('PLAGENOR — ESSBO', level=2)

    requester_name = (
        request_obj.requester.get_full_name()
        if request_obj.requester
        else request_obj.guest_name
    )

    table = doc.add_table(rows=9, cols=2)
    table.style = 'Light Grid Accent 1'
    fields = [
        ("Référence", request_obj.display_id),
        ("Code de suivi", str(request_obj.guest_token or request_obj.display_id)),
        ("Service", request_obj.service.code if request_obj.service else ''),
        ("Demandeur", requester_name),
        ("Canal", request_obj.channel),
        ("Date RDV", str(request_obj.appointment_date or '')),
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
