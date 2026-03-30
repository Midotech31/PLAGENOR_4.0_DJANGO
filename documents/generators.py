from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from django.conf import settings
from django.core.files import File
from pathlib import Path
from datetime import datetime


# Service code to IBTIKAR DOCX template filename mapping (fallback for static templates)
IBTIKAR_TEMPLATE_MAP = {
    'EGTP-CAN': 'egtp_can.docx',
    'EGTP-IMT': 'egtp_imt.docx',
    'EGTP-PCR': 'egtp_pcr.docx',
    'EGTP-Lyoph': 'egtp_lyoph.docx',
    'EGTP-PS': 'egtp_ps.docx',
    'EGTP-Seq02': 'egtp_seq02.docx',
    'EGTP-SeqS': 'egtp_seqs.docx',
    'EGTP-GDE': 'egtp_gde.docx',
    'EGTP-Illumina-Microbial-WGS': 'egtp_illumina_wgs.docx',
}


def _replace_placeholders(doc, replacements):
    """Replace placeholder text in all paragraphs and table cells of a Document."""
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


def _get_uploaded_template(service, template_type):
    """Check if there's an active uploaded template for this service and type."""
    from documents.models import ServiceTemplate
    
    try:
        template = ServiceTemplate.objects.filter(
            service=service,
            template_type=template_type,
            is_active=True
        ).first()
        
        if template and template.file:
            # Return the file path
            file_path = Path(settings.MEDIA_ROOT) / template.file.name
            if file_path.exists():
                return file_path
    except Exception:
        pass
    
    return None


def generate_ibtikar_form(request_obj) -> str:
    """Generate an IBTIKAR form DOCX for a request using service-specific official templates.
    
    Priority:
    1. Uploaded template from ServiceTemplate model (if exists)
    2. Static service-specific template from ibtikar/ directory
    3. Generic ibtikar_form_template.docx
    4. Programmatic generation as last resort
    
    Supported placeholders:
    - Requester: FULL_NAME, EMAIL, PHONE, ETABLISSEMENT, LABORATORY, SUPERVISOR, STUDENT_LEVEL
    - Service: SERVICE_CODE, SERVICE_NAME, SERVICE_DESCRIPTION
    - Request: DISPLAY_ID, REQUEST_ID, TITLE, DESCRIPTION, PROJECT_TITLE, BUDGET_AMOUNT, URGENCY, CHANNEL
    - Dates: DATE, SUBMISSION_DATE, APPOINTMENT_DATE
    - Assignment: ASSIGNED_ANALYST
    - Sample table: SAMPLE_TABLE (formatted as text)
    """
    # Helper to get requester info
    def get_requester_info():
        req = request_obj.requester
        if req:
            return {
                'FULL_NAME': req.get_full_name() or req.username,
                'EMAIL': getattr(req, 'email', '') or '',
                'PHONE': getattr(req, 'phone', '') or '',
                'ETABLISSEMENT': getattr(req, 'organization', '') or '',
                'LABORATORY': getattr(req, 'laboratory', '') or '',
                'SUPERVISOR': getattr(req, 'supervisor', '') or '',
                'STUDENT_LEVEL': getattr(req, 'student_level', '') or '',
            }
        return {
            'FULL_NAME': request_obj.guest_name or 'N/A',
            'EMAIL': request_obj.guest_email or '',
            'PHONE': request_obj.guest_phone or '',
            'ETABLISSEMENT': '',
            'LABORATORY': '',
            'SUPERVISOR': '',
            'STUDENT_LEVEL': '',
        }
    
    # Helper to get service info
    def get_service_info():
        svc = request_obj.service
        if svc:
            return {
                'SERVICE_CODE': svc.code,
                'SERVICE_NAME': svc.name,
                'SERVICE_DESCRIPTION': svc.description or '',
            }
        return {
            'SERVICE_CODE': 'N/A',
            'SERVICE_NAME': 'N/A',
            'SERVICE_DESCRIPTION': '',
        }
    
    # Build complete field map
    requester_info = get_requester_info()
    service_info = get_service_info()
    
    # Format sample table as a string for placeholder replacement
    sample_table_str = ''
    if request_obj.sample_table and isinstance(request_obj.sample_table, list):
        for i, sample in enumerate(request_obj.sample_table, 1):
            if isinstance(sample, dict):
                sample_str = f"#{i} "
                sample_str += " | ".join(f"{k}: {v}" for k, v in sample.items() if v)
                sample_table_str += sample_str + "\n"
    
    replacements = {
        # Dates
        'DATE': datetime.now().strftime('%d/%m/%Y'),
        'SUBMISSION_DATE': request_obj.created_at.strftime('%d/%m/%Y') if request_obj.created_at else datetime.now().strftime('%d/%m/%Y'),
        'APPOINTMENT_DATE': request_obj.appointment_date.strftime('%d/%m/%Y') if request_obj.appointment_date else 'Non défini',
        # Request IDs
        'DISPLAY_ID': request_obj.display_id,
        'REQUEST_ID': str(request_obj.pk),
        # Requester info
        **requester_info,
        # Aliases for IBTIKAR forms
        'GUEST_NAME': request_obj.guest_name or '',
        'GUEST_EMAIL': request_obj.guest_email or '',
        'GUEST_PHONE': request_obj.guest_phone or '',
        # Service info
        **service_info,
        # Request details
        'TITLE': request_obj.title,
        'PROJECT_TITLE': request_obj.title,  # Alias
        'DESCRIPTION': request_obj.description or '',
        'URGENCY': request_obj.urgency,
        'CHANNEL': request_obj.channel,
        # Budget
        'BUDGET_AMOUNT': f"{request_obj.budget_amount:,.0f} DZD" if request_obj.budget_amount else 'N/A',
        'IBTIKAR_BUDGET': f"{request_obj.budget_amount:,.0f} DZD" if request_obj.budget_amount else 'N/A',
        'IBTIKAR_BALANCE': f"{request_obj.declared_ibtikar_balance:,.0f} DZD" if request_obj.declared_ibtikar_balance else 'N/A',
        # Assignment
        'ASSIGNED_ANALYST': request_obj.assigned_to.user.get_full_name() if request_obj.assigned_to else 'Non assigné',
        # Sample table as string
        'SAMPLE_TABLE': sample_table_str,
    }

    doc = None
    template_source = None

    # 1) Try uploaded template from ServiceTemplate model
    if request_obj.service:
        uploaded_path = _get_uploaded_template(request_obj.service, 'IBTIKAR_FORM')
        if uploaded_path and uploaded_path.exists():
            doc = Document(str(uploaded_path))
            _replace_placeholders(doc, replacements)
            template_source = f"Uploaded template: {uploaded_path.name}"

    # 2) Try service-specific official template from ibtikar/ directory (fallback)
    if doc is None and request_obj.service:
        service_code = request_obj.service.code if request_obj.service else ''
        template_name = IBTIKAR_TEMPLATE_MAP.get(service_code, '')
        if template_name:
            template_path = Path(settings.BASE_DIR) / 'documents' / 'docx_templates' / 'ibtikar' / template_name
            if template_path.exists():
                doc = Document(str(template_path))
                _replace_placeholders(doc, replacements)
                template_source = f"Static template: {template_name}"

    # 3) Fall back to generic ibtikar_form_template.docx
    if doc is None:
        generic_path = Path(settings.BASE_DIR) / 'documents' / 'docx_templates' / 'ibtikar_form_template.docx'
        if generic_path.exists():
            doc = Document(str(generic_path))
            _replace_placeholders(doc, replacements)
            template_source = "Generic template"

    # 4) Fall back to programmatic generation
    if doc is None:
        doc = Document()
        doc.add_heading('Formulaire IBTIKAR — PLAGENOR', level=1)
        doc.add_heading("ESSBO — École Supérieure en Sciences Biologiques d'Oran", level=2)

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
        
        template_source = "Programmatic generation"

    out_dir = Path(settings.MEDIA_ROOT) / 'documents'
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"IBTIKAR_{request_obj.display_id}_{datetime.now().strftime('%Y%m%d')}.docx"
    filepath = out_dir / filename
    doc.save(str(filepath))
    return str(filepath)


def generate_platform_note(request_obj) -> str:
    """Generate a Platform Note dynamically populated from specific request data.
    
    Priority:
    1. Uploaded template from ServiceTemplate model (if exists)
    2. Static platform_note_template.docx
    3. Programmatic generation
    
    This function supports comprehensive placeholder replacement with the following keys:
    - Requester: FULL_NAME, EMAIL, PHONE, ETABLISSEMENT, LABORATORY, SUPERVISOR, STUDENT_LEVEL
    - Service: SERVICE_CODE, SERVICE_NAME, SERVICE_DESCRIPTION, TURNAROUND
    - Request: DISPLAY_ID, TITLE, DESCRIPTION, BUDGET_AMOUNT, URGENCY, CHANNEL
    - Dates: DATE, SUBMISSION_DATE, APPOINTMENT_DATE
    - Assignment: ASSIGNED_ANALYST, ANALYST_EMAIL
    - Budget (IBTIKAR): IBTIKAR_BUDGET, IBTIKAR_BALANCE, TOTAL_COST
    """
    doc = None
    
    # Helper to get requester info
    def get_requester_info():
        req = request_obj.requester
        if req:
            return {
                'FULL_NAME': req.get_full_name() or req.username,
                'EMAIL': getattr(req, 'email', '') or '',
                'PHONE': getattr(req, 'phone', '') or '',
                'ETABLISSEMENT': getattr(req, 'organization', '') or '',
                'LABORATORY': getattr(req, 'laboratory', '') or '',
                'SUPERVISOR': getattr(req, 'supervisor', '') or '',
                'STUDENT_LEVEL': getattr(req, 'student_level', '') or '',
            }
        return {
            'FULL_NAME': request_obj.guest_name or 'N/A',
            'EMAIL': request_obj.guest_email or '',
            'PHONE': request_obj.guest_phone or '',
            'ETABLISSEMENT': '',
            'LABORATORY': '',
            'SUPERVISOR': '',
            'STUDENT_LEVEL': '',
        }
    
    # Helper to get service info
    def get_service_info():
        svc = request_obj.service
        if svc:
            return {
                'SERVICE_CODE': svc.code,
                'SERVICE_NAME': svc.name,
                'SERVICE_DESCRIPTION': svc.description or '',
                'TURNAROUND': str(svc.turnaround_days) if svc.turnaround_days else 'N/A',
            }
        return {
            'SERVICE_CODE': 'N/A',
            'SERVICE_NAME': 'N/A',
            'SERVICE_DESCRIPTION': '',
            'TURNAROUND': 'N/A',
        }
    
    # Build complete field map
    requester_info = get_requester_info()
    service_info = get_service_info()
    
    # Format sample table as a string for placeholder replacement
    sample_table_str = ''
    if request_obj.sample_table and isinstance(request_obj.sample_table, list):
        for i, sample in enumerate(request_obj.sample_table, 1):
            if isinstance(sample, dict):
                sample_str = f"#{i} "
                sample_str += " | ".join(f"{k}: {v}" for k, v in sample.items() if v)
                sample_table_str += sample_str + "\n"
    
    # Format service params
    service_params_str = ''
    if request_obj.service_params and isinstance(request_obj.service_params, dict):
        for key, value in request_obj.service_params.items():
            clean_key = key.replace('param_', '').replace('_', ' ').title()
            service_params_str += f"{clean_key}: {value}\n"
    
    field_map = {
        # Dates
        'DATE': datetime.now().strftime('%d/%m/%Y'),
        'DATETIME': datetime.now().strftime('%d/%m/%Y à %H:%M'),
        'SUBMISSION_DATE': request_obj.created_at.strftime('%d/%m/%Y') if request_obj.created_at else datetime.now().strftime('%d/%m/%Y'),
        'APPOINTMENT_DATE': request_obj.appointment_date.strftime('%d/%m/%Y') if request_obj.appointment_date else 'Non défini',
        # Request IDs
        'DISPLAY_ID': request_obj.display_id,
        'REQUEST_ID': str(request_obj.pk),
        # Requester info
        **requester_info,
        # Service info
        **service_info,
        # Request details
        'TITLE': request_obj.title,
        'DESCRIPTION': request_obj.description or '',
        'URGENCY': request_obj.urgency,
        'CHANNEL': request_obj.channel,
        # Budget
        'BUDGET_AMOUNT': f"{request_obj.budget_amount:,.0f} DZD" if request_obj.budget_amount else 'N/A',
        'QUOTE_AMOUNT': f"{request_obj.quote_amount:,.0f} DZD" if request_obj.quote_amount else 'N/A',
        'FINAL_COST': f"{request_obj.admin_validated_price:,.0f} DZD" if request_obj.admin_validated_price else 'En attente',
        # IBTIKAR specific
        'IBTIKAR_BUDGET': f"{request_obj.budget_amount:,.0f} DZD" if request_obj.budget_amount else 'N/A',
        'IBTIKAR_BALANCE': f"{request_obj.declared_ibtikar_balance:,.0f} DZD" if request_obj.declared_ibtikar_balance else 'N/A',
        # Assignment
        'ASSIGNED_ANALYST': request_obj.assigned_to.user.get_full_name() if request_obj.assigned_to else 'Non assigné',
        'ANALYST_EMAIL': request_obj.assigned_to.user.email if request_obj.assigned_to else '',
        # Sample table as string (for simple templates)
        'SAMPLE_TABLE': sample_table_str,
        # Service params as string
        'SERVICE_PARAMS': service_params_str,
    }
    
    # 1) Try uploaded template
    if request_obj.service:
        uploaded_path = _get_uploaded_template(request_obj.service, 'PLATFORM_NOTE')
        if uploaded_path and uploaded_path.exists():
            doc = Document(str(uploaded_path))
            template_source = "Uploaded template"
    
    # 2) Fall back to static template
    if doc is None:
        template_path = Path(settings.BASE_DIR) / 'documents' / 'docx_templates' / 'platform_note_template.docx'
        if template_path.exists():
            doc = Document(str(template_path))
            template_source = "Static template"

    if doc is not None:
        # Template found, replace placeholders
        # Support {{KEY}}, [KEY], and bare KEY placeholder formats
        replacements = {}
        for key, value in field_map.items():
            replacements[f'{{{{{key}}}}}'] = value   # {{KEY}}
            replacements[f'[{key}]'] = value          # [KEY]
            replacements[key] = value                 # bare KEY

        _replace_placeholders(doc, replacements)
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
    out_dir = Path(settings.BASE_DIR) / 'media' / 'documents'
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"NOTE_PLT_{request_obj.display_id}_{datetime.now().strftime('%Y%m%d')}.docx"
    filepath = out_dir / filename
    doc.save(str(filepath))
    return str(filepath)


def generate_quote(request_obj) -> str:
    """Generate a GENOCLAB quote DOCX.
    
    Priority:
    1. Uploaded template from ServiceTemplate model (if exists)
    2. Static quote_template.docx
    3. Programmatic generation
    
    Supported placeholders:
    - Quote: QUOTE_NUMBER, DATE, QUOTE_AMOUNT, VAT_AMOUNT, TOTAL_TTC
    - Request: DISPLAY_ID, REQUEST_ID, TITLE, DESCRIPTION
    - Client: FULL_NAME, EMAIL, PHONE, ETABLISSEMENT, LABORATORY
    - Service: SERVICE_CODE, SERVICE_NAME
    """
    from core.models import Invoice
    
    # Sequential quote number
    quote_count = Invoice.objects.count() + 1
    quote_number = f"GENOCLAB-DEV-{datetime.now().year}-{quote_count:04d}"
    
    # Calculate amounts
    amount = float(request_obj.quote_amount or 0)
    vat_rate = float(settings.VAT_RATE)
    vat_amount = round(amount * vat_rate, 2)
    total_ttc = round(amount + vat_amount, 2)
    
    # Build field map
    def get_requester_info():
        req = request_obj.requester
        if req:
            return {
                'FULL_NAME': req.get_full_name() or req.username,
                'EMAIL': getattr(req, 'email', '') or '',
                'PHONE': getattr(req, 'phone', '') or '',
                'ETABLISSEMENT': getattr(req, 'organization', '') or '',
                'LABORATORY': getattr(req, 'laboratory', '') or '',
            }
        return {
            'FULL_NAME': request_obj.guest_name or 'N/A',
            'EMAIL': request_obj.guest_email or '',
            'PHONE': request_obj.guest_phone or '',
            'ETABLISSEMENT': '',
            'LABORATORY': '',
        }
    
    field_map = {
        **get_requester_info(),
        # Quote info
        'QUOTE_NUMBER': quote_number,
        'DATE': datetime.now().strftime('%d/%m/%Y'),
        'QUOTE_AMOUNT': f"{amount:,.2f} DA",
        'VAT_RATE': f"{vat_rate * 100:.0f}%",
        'VAT_AMOUNT': f"{vat_amount:,.2f} DA",
        'TOTAL_TTC': f"{total_ttc:,.2f} DA",
        'SUBTOTAL_HT': f"{amount:,.2f} DA",
        # Request info
        'DISPLAY_ID': request_obj.display_id,
        'REQUEST_ID': str(request_obj.pk),
        'TITLE': request_obj.title,
        'DESCRIPTION': request_obj.description or '',
        # Service info
        'SERVICE_CODE': request_obj.service.code if request_obj.service else 'N/A',
        'SERVICE_NAME': request_obj.service.name if request_obj.service else request_obj.title,
    }
    
    doc = None
    
    # 1) Try uploaded template
    if request_obj.service:
        uploaded_path = _get_uploaded_template(request_obj.service, 'QUOTE')
        if uploaded_path and uploaded_path.exists():
            doc = Document(str(uploaded_path))
    
    # 2) Fall back to static template
    if doc is None:
        template_path = Path(settings.BASE_DIR) / 'documents' / 'docx_templates' / 'quote_template.docx'
        if template_path.exists():
            doc = Document(str(template_path))
    
    if doc is not None:
        # Template found, replace placeholders
        replacements = {}
        for key, value in field_map.items():
            replacements[f'{{{{{key}}}}}'] = value
            replacements[f'[{key}]'] = value
            replacements[key] = value
        _replace_placeholders(doc, replacements)
    else:
        # Programmatic generation
        doc = Document()
        doc.add_heading('Devis — GENOCLAB', level=1)
        doc.add_heading("ESSBO — École Supérieure en Sciences Biologiques d'Oran", level=2)

        doc.add_paragraph(f"N° Devis: {quote_number}")
        doc.add_paragraph(f"Référence demande: {request_obj.display_id}")
        doc.add_paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y')}")
        doc.add_paragraph('')

        # Client info
        doc.add_heading('Informations client', level=3)
        requester_info = get_requester_info()
        doc.add_paragraph(f"Client: {requester_info['FULL_NAME']}")
        doc.add_paragraph(f"Organisation: {requester_info['ETABLISSEMENT']}")
        doc.add_paragraph(f"Email: {requester_info['EMAIL']}")

        # Service details + line items
        doc.add_heading('Prestations', level=3)
        table = doc.add_table(rows=2, cols=4)
        table.style = 'Light Grid Accent 1'
        headers = ['Description', 'Quantité', 'Prix unitaire', 'Total']
        for i, h in enumerate(headers):
            table.rows[0].cells[i].text = h

        service_name = field_map['SERVICE_NAME']
        table.rows[1].cells[0].text = service_name
        table.rows[1].cells[1].text = '1'
        table.rows[1].cells[2].text = f"{amount:,.2f} DA"
        table.rows[1].cells[3].text = f"{amount:,.2f} DA"

        doc.add_paragraph('')

        summary_table = doc.add_table(rows=3, cols=2)
        summary_table.rows[0].cells[0].text = 'Sous-total HT'
        summary_table.rows[0].cells[1].text = f"{amount:,.2f} DA"
        summary_table.rows[1].cells[0].text = f'TVA ({vat_rate * 100:.0f}%)'
        summary_table.rows[1].cells[1].text = f"{vat_amount:,.2f} DA"
        summary_table.rows[2].cells[0].text = 'Total TTC'
        summary_table.rows[2].cells[1].text = f"{total_ttc:,.2f} DA"

    out_dir = Path(settings.MEDIA_ROOT) / 'documents'
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"DEVIS_{request_obj.display_id}_{datetime.now().strftime('%Y%m%d')}.docx"
    filepath = out_dir / filename
    doc.save(str(filepath))
    return str(filepath)


def generate_reception_form(request_obj) -> str:
    """Generate comprehensive sample reception form DOCX for GENOCLAB.
    
    Priority:
    1. Uploaded template from ServiceTemplate model (if exists)
    2. Static reception_form_template.docx
    3. Programmatic generation
    
    Supported placeholders:
    - Request: DISPLAY_ID, REQUEST_ID, TRACKING_CODE, TITLE, CHANNEL, URGENCY
    - Dates: DATE, APPOINTMENT_DATE, SUBMISSION_DATE
    - Client: FULL_NAME, EMAIL, PHONE, ETABLISSEMENT, LABORATORY
    - Service: SERVICE_CODE, SERVICE_NAME
    - Assignment: ASSIGNED_ANALYST
    - Sample table: SAMPLE_TABLE (formatted as table)
    """
    # Build field map
    def get_requester_info():
        req = request_obj.requester
        if req:
            return {
                'FULL_NAME': req.get_full_name() or req.username,
                'EMAIL': getattr(req, 'email', '') or '',
                'PHONE': getattr(req, 'phone', '') or '',
                'ETABLISSEMENT': getattr(req, 'organization', '') or '',
                'LABORATORY': getattr(req, 'laboratory', '') or '',
            }
        return {
            'FULL_NAME': request_obj.guest_name or 'N/A',
            'EMAIL': request_obj.guest_email or '',
            'PHONE': request_obj.guest_phone or '',
            'ETABLISSEMENT': '',
            'LABORATORY': '',
        }
    
    field_map = {
        **get_requester_info(),
        # Request info
        'DISPLAY_ID': request_obj.display_id,
        'REQUEST_ID': str(request_obj.pk),
        'TRACKING_CODE': str(request_obj.guest_token or request_obj.display_id),
        'TITLE': request_obj.title,
        'CHANNEL': request_obj.channel,
        'URGENCY': request_obj.urgency,
        # Dates
        'DATE': datetime.now().strftime('%d/%m/%Y'),
        'APPOINTMENT_DATE': request_obj.appointment_date.strftime('%d/%m/%Y') if request_obj.appointment_date else 'Non défini',
        'SUBMISSION_DATE': request_obj.created_at.strftime('%d/%m/%Y') if request_obj.created_at else datetime.now().strftime('%d/%m/%Y'),
        # Service info
        'SERVICE_CODE': request_obj.service.code if request_obj.service else 'N/A',
        'SERVICE_NAME': request_obj.service.name if request_obj.service else 'N/A',
        # Assignment
        'ASSIGNED_ANALYST': request_obj.assigned_to.user.get_full_name() if request_obj.assigned_to else 'Non assigné',
    }
    
    doc = None
    
    # 1) Try uploaded template
    if request_obj.service:
        uploaded_path = _get_uploaded_template(request_obj.service, 'RECEPTION_FORM')
        if uploaded_path and uploaded_path.exists():
            doc = Document(str(uploaded_path))
    
    # 2) Fall back to static template
    if doc is None:
        template_path = Path(settings.BASE_DIR) / 'documents' / 'docx_templates' / 'reception_form_template.docx'
        if template_path.exists():
            doc = Document(str(template_path))
    
    if doc is not None:
        # Template found, replace placeholders
        replacements = {}
        for key, value in field_map.items():
            replacements[f'{{{{{key}}}}}'] = value
            replacements[f'[{key}]'] = value
            replacements[key] = value
        _replace_placeholders(doc, replacements)
    else:
        # Programmatic generation
        doc = Document()
        doc.add_heading("Fiche de Réception d'Échantillons", level=1)
        doc.add_heading('PLAGENOR — ESSBO', level=2)

        # Request reference info
        table = doc.add_table(rows=6, cols=2)
        table.style = 'Light Grid Accent 1'
        fields = [
            ("Référence", field_map['DISPLAY_ID']),
            ("Code de suivi", field_map['TRACKING_CODE']),
            ("Service", field_map['SERVICE_NAME']),
            ("Canal", field_map['CHANNEL']),
            ("Date RDV", field_map['APPOINTMENT_DATE']),
            ("Urgence", field_map['URGENCY']),
        ]
        for i, (label, value) in enumerate(fields):
            table.rows[i].cells[0].text = label
            table.rows[i].cells[1].text = str(value)

        # Client info
        doc.add_heading('Informations du déposant', level=2)
        client_table = doc.add_table(rows=5, cols=2)
        client_table.style = 'Light Grid Accent 1'
        client_fields = [
            ("Nom", field_map['FULL_NAME']),
            ("Email", field_map['EMAIL']),
            ("Téléphone", field_map['PHONE']),
            ("Établissement", field_map['ETABLISSEMENT']),
            ("Laboratoire", field_map['LABORATORY']),
        ]
        for i, (label, value) in enumerate(client_fields):
            client_table.rows[i].cells[0].text = label
            client_table.rows[i].cells[1].text = str(value)

        # Sample table
        if request_obj.sample_table:
            doc.add_heading('Tableau des échantillons', level=2)
            samples = request_obj.sample_table
            if isinstance(samples, list) and samples and isinstance(samples[0], dict):
                headers = list(samples[0].keys())
                sample_count = len([s for s in samples if any(s.values())])  # Count non-empty samples
                t = doc.add_table(rows=sample_count + 1, cols=len(headers))
                t.style = 'Light Grid Accent 1'
                for j, h in enumerate(headers):
                    t.rows[0].cells[j].text = h.replace('_', ' ').title()
                row_idx = 1
                for sample in samples:
                    if any(sample.values()):  # Only add non-empty samples
                        for j, h in enumerate(headers):
                            t.rows[row_idx].cells[j].text = str(sample.get(h, ''))
                        row_idx += 1

        # Reception details
        doc.add_heading('Réception', level=2)
        reception_table = doc.add_table(rows=4, cols=2)
        reception_table.style = 'Light Grid Accent 1'
        reception_fields = [
            ("Date de réception", "___/___/______"),
            ("Nombre d'échantillons reçus", "____________"),
            ("État des échantillons", "□ Bon  □ Acceptable  □ Dégradé"),
            ("Observations", ""),
        ]
        for i, (label, value) in enumerate(reception_fields):
            reception_table.rows[i].cells[0].text = label
            reception_table.rows[i].cells[1].text = str(value)

        # Signatures
        doc.add_paragraph("\n")
        doc.add_paragraph("Signature du réceptionniste: ________________")
        doc.add_paragraph("Signature du déposant: ________________")
        doc.add_paragraph("\n")
        doc.add_paragraph("—" * 40)
        doc.add_paragraph(f"Document généré par PLAGENOR 4.0 | {datetime.now().strftime('%d/%m/%Y à %H:%M')}")

    out_dir = Path(settings.MEDIA_ROOT) / 'documents'
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"RECEPTION_{request_obj.display_id}_{datetime.now().strftime('%Y%m%d')}.docx"
    filepath = out_dir / filename
    doc.save(str(filepath))
    return str(filepath)


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

    out_dir = Path(settings.MEDIA_ROOT) / 'documents'
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"INVOICE_{invoice_obj.invoice_number}.docx"
    filepath = out_dir / filename
    doc.save(str(filepath))
    return str(filepath)
