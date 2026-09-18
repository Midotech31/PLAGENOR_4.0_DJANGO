from copy import deepcopy
from datetime import datetime
import io
import json
from pathlib import Path
import uuid

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


TEXT = {
    'form': ('FICHE DE DEMANDE IBTIKAR', 'IBTIKAR REQUEST FORM', 'استمارة طلب إبتكار'),
    'requester': ('Demandeur et projet', 'Applicant and project', 'صاحب الطلب والمشروع'),
    'parameters': ('Paramètres de la prestation', 'Service parameters', 'معلمات الخدمة'),
    'samples': ('Échantillons / amorces', 'Samples / primers', 'العينات / البادئات'),
    'sample': ('Échantillon / amorce', 'Sample / primer', 'العينة / البادئ'),
    'staff': ('Cadre réservé à PLAGENOR', 'PLAGENOR section', 'إطار مخصص للأرضية'),
    'attachments': ('Documents joints applicables', 'Applicable attachments', 'الوثائق المرفقة المعنية'),
    'signature': ('Signature du demandeur', 'Applicant signature', 'توقيع صاحب الطلب'),
    'operator_signature': ('Signature de l’opérateur', 'Operator signature', 'توقيع الموظف المكلف'),
    'head': ('Visa du Chef du Service Commun', 'Common Service Head endorsement', 'تأشيرة رئيس المصلحة المشتركة'),
    'director': ('Visa du Directeur de l’ESSBO', 'ESSBO Director endorsement', 'تأشيرة مدير المدرسة'),
    'unknown': ('Non renseigné', 'Not provided', 'غير مذكور'),
    'source': ('Formulaire source', 'Source form', 'الاستمارة المرجعية'),
    'revision': ('Révision numérique', 'Digital revision', 'المراجعة الرقمية'),
    'date': ('Date de la demande', 'Request date', 'تاريخ الطلب'),
    'number': ('Numéro de demande', 'Request number', 'رقم الطلب'),
    'count': ('Nombre de lignes enregistrées', 'Number of recorded rows', 'عدد الصفوف المسجلة'),
    'reads': ('Nombre de lectures demandé', 'Requested number of reads', 'عدد القراءات المطلوبة'),
    'legacy': ('Données historiques conservées — aucune valeur absente n’est déduite du modèle papier.',
               'Historical data retained — no missing value is inferred from the paper template.',
               'بيانات تاريخية محفوظة — لا تستنتج القيم الغائبة من النموذج الورقي.'),
    'unsigned': ('Un nom ou un visa saisi ne constitue pas une signature manuscrite. Les emplacements non signés restent à compléter.',
                 'A typed name or endorsement is not a handwritten signature. Unsigned areas remain to be completed.',
                 'لا يعد الاسم أو التأشير المكتوب توقيعا بخط اليد. تبقى مواضع التوقيع الفارغة لاستكمالها.'),
    'draft': ('BROUILLON — demande non soumise', 'DRAFT — request not submitted', 'مسودة — لم يرسل الطلب'),
    'reference': ('Référence IBTIKAR-DGRSDT', 'IBTIKAR-DGRSDT reference', 'مرجع إبتكار للمديرية العامة للبحث العلمي'),
    'operator': ('Opérateur ayant enregistré la réception', 'Operator recording receipt', 'الموظف الذي سجل الاستلام'),
}


def text(key, language):
    return TEXT[key][{'fr': 0, 'en': 1, 'ar': 2}.get(language, 0)]


def _direction(paragraph, rtl):
    if rtl:
        ppr = paragraph._p.get_or_add_pPr()
        bidi = OxmlElement('w:bidi')
        ppr.append(bidi)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT


def _table(doc, rows, language):
    if not rows:
        return
    table = doc.add_table(rows=0, cols=2)
    table.autofit = False
    table.columns[0].width = Cm(6.0)
    table.columns[1].width = Cm(11.0)
    for row in rows:
        cells = table.add_row().cells
        cells[0].width = Cm(6.0)
        cells[1].width = Cm(11.0)
        cells[0].text = str(row['label'])
        selected = [('☑ ' if option['selected'] else '☐ ') + option['label'] for option in row.get('options', []) if option['selected'] or row.get('all_options')]
        cells[1].text = '\n'.join(selected) if selected else str(row['display'])
        for j, cell in enumerate(cells):
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(2)
                p.paragraph_format.space_before = Pt(1)
                _direction(p, language == 'ar')
                for run in p.runs:
                    run.font.size = Pt(10)
                    if j == 0:
                        run.bold = True
            tcpr = cell._tc.get_or_add_tcPr()
            margins = OxmlElement('w:tcMar')
            for name in ('top', 'left', 'bottom', 'right'):
                element = OxmlElement('w:' + name)
                element.set(qn('w:w'), '45')
                element.set(qn('w:type'), 'dxa')
                margins.append(element)
            tcpr.append(margins)
            if j == 0:
                shading = OxmlElement('w:shd'); shading.set(qn('w:fill'), 'F1F5F9'); tcpr.append(shading)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def build_document(project, metadata, language='fr', attachment_rows=None, signature_bytes=None, legacy=None):
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(2.0), Cm(1.9)
    section.left_margin = section.right_margin = Cm(2.0)
    normal = doc.styles['Normal']
    normal.font.name = 'Arial'; normal.font.size = Pt(10)
    normal.paragraph_format.line_spacing = 1.04
    normal.paragraph_format.space_after = Pt(2)
    for name, size in [('Title', 18), ('Heading 1', 13), ('Heading 2', 11)]:
        style = doc.styles[name]; style.font.name = 'Arial'; style.font.size = Pt(size)
        style.font.color.rgb = RGBColor.from_string('24364B')
        style.paragraph_format.keep_with_next = True
    header = section.header.paragraphs[0]
    header.text = 'ESSBO  |  PLAGENOR'
    header.runs[0].bold = True
    header.runs[0].font.size = Pt(9)
    p = doc.add_paragraph(text('form', language), 'Title'); _direction(p, language == 'ar')
    p = doc.add_paragraph(project['title']); p.runs[0].bold = True; _direction(p, language == 'ar')
    doc.add_paragraph({'fr': 'École Supérieure en Sciences Biologiques d’Oran — PLAGENOR', 'en': 'Higher School of Biological Sciences of Oran — PLAGENOR', 'ar': 'المدرسة العليا في العلوم البيولوجية بوهران — الأرضية التكنولوجية للجينوميك'}.get(language, 'ESSBO — PLAGENOR'))
    if metadata.get('draft'):
        doc.add_paragraph(text('draft', language), 'Heading 2')
    _table(doc, [{'label': text('number', language), 'display': metadata['number']},
                 {'label': text('date', language), 'display': metadata['date']},
                 {'label': text('source', language), 'display': project.get('source_version') or text('unknown', language)},
                 {'label': text('revision', language), 'display': str(metadata.get('revision') or text('unknown', language))},
                 {'label': 'Code', 'display': project['service_code']},
                 {'label': text('reference', language), 'display': metadata.get('external_reference') or text('unknown', language)},
                 {'label': text('count', language), 'display': project.get('sample_count', 0)}], language)
    if legacy:
        doc.add_paragraph(text('legacy', language))
    for key in ('applicant', 'parameters'):
        if project.get(key):
            doc.add_heading(text('requester' if key == 'applicant' else key, language), level=1)
            _table(doc, project[key], language)
    if project.get('samples'):
        doc.add_heading(text('samples', language), level=1)
        if project.get('read_count') is not None:
            doc.add_paragraph(f"{text('reads', language)} : {project['read_count']}")
        for index, rows in enumerate(project['samples'], 1):
            doc.add_heading(f"{text('sample', language)} {index}", level=2)
            _table(doc, rows, language)
    if attachment_rows:
        doc.add_heading(text('attachments', language), level=1)
        _table(doc, attachment_rows, language)
    if project.get('notices'):
        for notice in project['notices']:
            doc.add_paragraph(notice)
    doc.add_heading(text('signature', language), level=1)
    if signature_bytes:
        doc.add_picture(io.BytesIO(signature_bytes), width=Cm(4.0))
    else:
        doc.add_paragraph('_________________________________________________________________')
    doc.add_heading(text('staff', language), level=1)
    if metadata.get('operator_name'):
        doc.add_paragraph(f"{text('operator', language)} : {metadata['operator_name']}")
    staff_rows = project.get('staff') or []
    _table(doc, staff_rows, language)
    if staff_rows:
        for row in doc.tables[-1].rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.keep_with_next = True
        doc.paragraphs[-1].paragraph_format.keep_with_next = True
    for key in ('operator_signature', 'head', 'director'):
        paragraph = doc.add_paragraph(text(key, language) + ' : ________________________________________')
        paragraph.paragraph_format.keep_with_next = True
    doc.add_paragraph(text('unsigned', language))
    if legacy:
        doc.add_heading(text('legacy', language), level=1)
        for key, value in legacy.items():
            p = doc.add_paragraph(str(key)); p.runs[0].bold = True
            doc.add_paragraph(json.dumps(value, ensure_ascii=False, indent=2))
    footer = section.footer.paragraphs[0]
    footer.text = f"PLAGENOR · {metadata['number']} · "
    field = OxmlElement('w:fldSimple'); field.set(qn('w:instr'), 'PAGE'); footer._p.append(field)
    for run in footer.runs: run.font.size = Pt(8)
    for paragraph in doc.paragraphs:
        _direction(paragraph, language == 'ar')
    return doc


def generate_canonical_form(req):
    from django.conf import settings
    from django.utils.translation import get_language
    from core.ibtikar.models import IbtikarSubmission
    from core.ibtikar.schema import get_schema, projection, active_names, label, schema_for_service, active_data
    from core.ibtikar.legacy import legacy_initial
    from documents.docx_helpers import ensure_institutional_header
    language = (get_language() or 'fr').split('-')[0]
    submission = IbtikarSubmission.objects.filter(request=req).first()
    attachments = []
    signature = None
    legacy = None
    if submission:
        schema = submission.schema
        project = projection(schema, submission.applicant, submission.parameters,
                             submission.samples, submission.staff, language, print_blank_staff=True)
        active = active_names(schema['attachments'], {}, submission.parameters, [active_data(schema, 'samples', row, submission.parameters) for row in submission.samples])
        for obj in submission.attachments.filter(active=True):
            if obj.field_name not in active:
                continue
            spec = next((f for f in schema['attachments'] if f['name'] == obj.field_name), None)
            if spec:
                attachments.append({'label': label(spec['label'], language), 'display': obj.original_name})
                if obj.field_name == 'applicant_signature':
                    with obj.file.open('rb') as stream:
                        signature = stream.read()
        legacy = None
    else:
        schema = schema_for_service(req.service)
        old = legacy_initial(req, schema)
        project = projection(schema, old['applicant'], old['parameters'], old['samples'], language=language, print_blank_staff=True)
        project['source_version'] = text('unknown', language)
        legacy = old['legacy_data']
    project['staff'] = [row for row in project['staff'] if row['name'] not in ('validated_price', 'price_justification')]
    metadata = {'number': req.display_id, 'date': req.created_at.strftime('%d/%m/%Y'),
                'external_reference': req.ibtikar_external_code,
                'revision': submission.revision if submission else None, 'draft': req.status == 'DRAFT',
                'operator_name': submission.staff.get('operator_name') if submission else None}
    doc = build_document(project, metadata, language, attachments, signature, legacy)
    ensure_institutional_header(doc)
    from documents.generators import _inject_document_blocks
    _inject_document_blocks(doc, 'IBTIKAR_FORM', req)
    directory = Path(settings.MEDIA_ROOT) / 'documents'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'IBTIKAR_{req.pk}_{uuid.uuid4().hex}.docx'
    doc.save(path)
    return str(path)
