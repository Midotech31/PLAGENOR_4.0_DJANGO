from copy import deepcopy
import io
import json
from pathlib import Path
import re
import uuid

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from documents.document_design import (
    PLAGENOR_THEME, add_callout, add_document_footer, add_document_title,
    add_identity_header, add_section_heading, add_signature_grid,
    apply_document_style, set_cant_split, style_data_table, style_key_value_table,
)
from documents.ibtikar_reference import reference_content


TEXT = {
    'form': ('FICHE DE DEMANDE IBTIKAR', 'IBTIKAR REQUEST FORM', 'استمارة طلب إبتكار'),
    'requester': ('Demandeur et projet', 'Applicant and project', 'صاحب الطلب والمشروع'),
    'parameters': ('Paramètres de la prestation', 'Service parameters', 'معلمات الخدمة'),
    'samples': ('Échantillons / amorces', 'Samples / primers', 'العينات / البادئات'),
    'sample': ('Échantillon / amorce', 'Sample / primer', 'العينة / البادئ'),
    'guidance': ('Exigences, sécurité et conditions', 'Requirements, safety and conditions', 'المتطلبات والسلامة والشروط'),
    'staff': ('Cadre réservé à PLAGENOR', 'PLAGENOR section', 'إطار مخصص للأرضية'),
    'attachments': ('Documents joints applicables', 'Applicable attachments', 'الوثائق المرفقة المعنية'),
    'ethics': ('Déclaration de responsabilité éthique', 'Ethical responsibility statement', 'إقرار المسؤولية الأخلاقية'),
    'signature': ('Signature du demandeur', 'Applicant signature', 'توقيع صاحب الطلب'),
    'operator_signature': ('Signature de l’opérateur', 'Operator signature', 'توقيع الموظف المكلف'),
    'head': ('Visa du Chef du Service Commun', 'Common Service Head endorsement', 'تأشيرة رئيس المصلحة المشتركة'),
    'director': ('Visa du Directeur de l’ESSBO', 'ESSBO Director endorsement', 'تأشيرة مدير المدرسة'),
    'unknown': ('Non renseigné', 'Not provided', 'غير مذكور'),
    'source': ('Version du formulaire source', 'Source form version', 'نسخة الاستمارة المرجعية'),
    'revision': ('Révision numérique', 'Digital revision', 'المراجعة الرقمية'),
    'date': ('Date de la demande', 'Request date', 'تاريخ الطلب'),
    'number': ('Numéro de demande', 'Request number', 'رقم الطلب'),
    'count': ('Nombre de lignes enregistrées', 'Number of recorded rows', 'عدد الصفوف المسجلة'),
    'reads': ('Nombre de lectures demandé', 'Requested number of reads', 'عدد القراءات المطلوبة'),
    'reference': ('Référence IBTIKAR-DGRSDT', 'IBTIKAR-DGRSDT reference', 'مرجع إبتكار للمديرية العامة للبحث العلمي'),
    'operator': ('Opérateur ayant enregistré la réception', 'Operator recording receipt', 'الموظف الذي سجل الاستلام'),
    'legacy': ('Données historiques conservées — aucune valeur absente n’est déduite du modèle papier.',
               'Historical data retained — no missing value is inferred from the paper template.',
               'بيانات تاريخية محفوظة — لا تستنتج القيم الغائبة من النموذج الورقي.'),
    'unsigned': ('Un nom ou un visa saisi ne constitue pas une signature manuscrite. Les emplacements non signés restent à compléter.',
                 'A typed name or endorsement is not a handwritten signature. Unsigned areas remain to be completed.',
                 'لا يعد الاسم أو التأشير المكتوب توقيعا بخط اليد. تبقى مواضع التوقيع الفارغة لاستكمالها.'),
    'draft': ('BROUILLON — demande non soumise', 'DRAFT — request not submitted', 'مسودة — لم يرسل الطلب'),
    'ethics_body': (
        "La signature de cette fiche atteste que les échantillons soumis ont été collectés, manipulés et transférés conformément aux exigences éthiques et réglementaires applicables. Le demandeur assume la responsabilité de leur nature, de leur origine et de leur utilisation.",
        "Signing this form certifies that the submitted samples were collected, handled and transferred in accordance with applicable ethical and regulatory requirements. The applicant accepts responsibility for their nature, origin and use.",
        "يقر توقيع هذه الاستمارة بأن العينات المقدمة جُمعت وعولجت ونُقلت وفقا للمتطلبات الأخلاقية والتنظيمية المعمول بها، ويتحمل صاحب الطلب مسؤولية طبيعتها ومصدرها واستعمالها.",
    ),
}


def text(key, language):
    return TEXT[key][{'fr': 0, 'en': 1, 'ar': 2}.get(language, 0)]


def _direction(paragraph, rtl):
    if not rtl:
        return
    ppr = paragraph._p.get_or_add_pPr()
    if ppr.find(qn('w:bidi')) is None:
        ppr.append(OxmlElement('w:bidi'))
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT


def _rtl_document(doc, language):
    if language != 'ar':
        return
    for paragraph in doc.paragraphs:
        _direction(paragraph, True)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _direction(paragraph, True)


def _display(row):
    selected = [
        ('☑ ' if option['selected'] else '☐ ') + option['label']
        for option in row.get('options', [])
        if option['selected'] or row.get('all_options')
    ]
    return '\n'.join(selected) if selected else str(row.get('display', ''))


def _kv_table(doc, rows, language, *, dense=False):
    if not rows:
        return None
    table = doc.add_table(rows=0, cols=2)
    table.autofit = False
    table.columns[0].width = Cm(6.1)
    table.columns[1].width = Cm(11.0)
    for item in rows:
        cells = table.add_row().cells
        cells[0].width, cells[1].width = Cm(6.1), Cm(11.0)
        cells[0].text = str(item['label'])
        cells[1].text = _display(item)
        set_cant_split(table.rows[-1])
    style_key_value_table(table, theme=PLAGENOR_THEME, dense=dense)
    if language == 'ar':
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _direction(paragraph, True)
    return table


def _control_table(doc, project, metadata, language):
    rows = [
        {'label': text('number', language), 'display': metadata['number']},
        {'label': text('date', language), 'display': metadata['date']},
        {'label': text('source', language), 'display': project.get('source_version') or text('unknown', language)},
        {'label': text('revision', language), 'display': str(metadata.get('revision') or text('unknown', language))},
        {'label': 'Code', 'display': project['service_code']},
        {'label': text('reference', language), 'display': metadata.get('external_reference') or text('unknown', language)},
        {'label': text('count', language), 'display': project.get('sample_count', 0)},
    ]
    return _kv_table(doc, rows, language, dense=True)


def _sample_columns(samples):
    names, labels = [], {}
    for rows in samples:
        for row in rows:
            name = row.get('name') or row.get('label')
            if name not in names:
                names.append(name)
                labels[name] = row.get('label') or name
    return names, labels


def _render_samples(doc, project, language):
    samples = project.get('samples') or []
    if not samples:
        return
    add_section_heading(doc, text('samples', language), theme=PLAGENOR_THEME)
    if project.get('read_count') is not None:
        p = doc.add_paragraph(f"{text('reads', language)} : {project['read_count']}")
        p.paragraph_format.space_after = Pt(5)
    names, labels = _sample_columns(samples)
    compact = len(names) <= 6 and sum(len(str(labels[n])) for n in names) <= 130
    if compact:
        table = doc.add_table(rows=1, cols=len(names) + 1)
        table.autofit = False
        table.rows[0].cells[0].text = 'N°'
        for index, name in enumerate(names, 1):
            table.rows[0].cells[index].text = str(labels[name])
        for number, rows in enumerate(samples, 1):
            values = {row.get('name') or row.get('label'): _display(row) for row in rows}
            cells = table.add_row().cells
            cells[0].text = f'{number:02d}'
            for index, name in enumerate(names, 1):
                cells[index].text = str(values.get(name, '—'))
        style_data_table(table, theme=PLAGENOR_THEME, dense=True)
        return
    for number, rows in enumerate(samples, 1):
        add_section_heading(doc, f"{text('sample', language)} {number:02d}",
                            theme=PLAGENOR_THEME, level=2)
        _kv_table(doc, rows, language, dense=True)


def _looks_heading(value):
    clean = value.strip()
    if not clean or len(clean) > 95:
        return False
    return bool(re.match(r'^\d+\.\s', clean)) or clean.endswith(':') or clean.lower().startswith(
        ('conditions ', 'sécurité ', 'critères ', 'autres récipients', 'acknowledgment ')
    )


def _render_reference(doc, project, language):
    source = reference_content(project['service_code'])
    if language != 'fr' and (source.get('guidance') or source.get('tables')):
        note = {
            'en': 'The operational requirements below are preserved in their official French source wording.',
            'ar': 'تُحفظ المتطلبات التشغيلية أدناه بصياغتها الرسمية الأصلية باللغة الفرنسية.',
        }.get(language)
        if note:
            add_callout(doc, note, theme=PLAGENOR_THEME)
    guidance = list(source.get('guidance') or [])
    for notice in project.get('notices') or []:
        if notice and not any(notice.casefold() in value.casefold() or value.casefold() in notice.casefold()
                              for value in guidance if value):
            guidance.append(notice)
    blocks = list(source.get('blocks') or [])
    source_paragraphs = {
        block.get('text') for block in blocks if block.get('type') == 'paragraph'
    }
    for notice in guidance:
        if notice not in source_paragraphs:
            blocks.append({'type': 'paragraph', 'text': notice})
    if blocks:
        add_section_heading(doc, text('guidance', language), theme=PLAGENOR_THEME)
        for block in blocks:
            if block.get('type') == 'table':
                rows = block.get('rows') or []
                if not rows:
                    continue
                table = doc.add_table(rows=0, cols=max(len(row) for row in rows))
                for row_values in rows:
                    cells = table.add_row().cells
                    for index, value in enumerate(row_values):
                        cells[index].text = str(value)
                style_data_table(table, theme=PLAGENOR_THEME, dense=True)
                continue
            value = block.get('text') or ''
            if value.lower().startswith(('très important', 'important')):
                add_callout(doc, value, title='Important', theme=PLAGENOR_THEME, kind='warning')
            elif _looks_heading(value):
                add_section_heading(doc, value, theme=PLAGENOR_THEME, level=2)
            else:
                p = doc.add_paragraph(value)
                p.paragraph_format.space_after = Pt(3)
    return source.get('ethics') or text('ethics_body', language)


def _render_attachments(doc, rows, language):
    if not rows:
        return
    add_section_heading(doc, text('attachments', language), theme=PLAGENOR_THEME)
    _kv_table(doc, rows, language, dense=True)


def _signature_image(doc, signature_bytes):
    if signature_bytes:
        try:
            doc.add_picture(io.BytesIO(signature_bytes), width=Cm(4.0))
            return
        except Exception:
            pass
    table = doc.add_table(rows=1, cols=1)
    cell = table.cell(0, 0)
    cell.text = '\n\n'
    from documents.document_design import set_cell_border, set_cell_margins
    set_cell_border(cell, top=(PLAGENOR_THEME.line, 3), bottom=(PLAGENOR_THEME.line, 3),
                    start=(PLAGENOR_THEME.line, 3), end=(PLAGENOR_THEME.line, 3))
    set_cell_margins(cell, top=120, bottom=360, start=120, end=120)


def build_document(project, metadata, language='fr', attachment_rows=None,
                   signature_bytes=None, legacy=None):
    doc = Document()
    apply_document_style(doc, PLAGENOR_THEME, dense=True)
    add_identity_header(doc, PLAGENOR_THEME, compact=True)
    add_document_title(
        doc, text('form', language),
        subtitle=project['title'], code=project['service_code'],
        theme=PLAGENOR_THEME,
    )
    if metadata.get('draft'):
        add_callout(doc, text('draft', language), theme=PLAGENOR_THEME, kind='warning')
    _control_table(doc, project, metadata, language)
    if legacy:
        add_callout(doc, text('legacy', language), theme=PLAGENOR_THEME)
    if project.get('applicant'):
        add_section_heading(doc, text('requester', language), theme=PLAGENOR_THEME)
        _kv_table(doc, project['applicant'], language)
    if project.get('parameters'):
        add_section_heading(doc, text('parameters', language), theme=PLAGENOR_THEME)
        _kv_table(doc, project['parameters'], language)
    _render_samples(doc, project, language)
    _render_attachments(doc, attachment_rows or [], language)
    ethics = _render_reference(doc, project, language)
    add_section_heading(doc, text('ethics', language), theme=PLAGENOR_THEME)
    add_callout(doc, ethics, theme=PLAGENOR_THEME)
    add_section_heading(doc, text('signature', language), theme=PLAGENOR_THEME)
    _signature_image(doc, signature_bytes)
    add_section_heading(doc, text('staff', language), theme=PLAGENOR_THEME)
    if metadata.get('operator_name'):
        p = doc.add_paragraph(f"{text('operator', language)} : {metadata['operator_name']}")
        p.paragraph_format.keep_with_next = True
    staff_rows = project.get('staff') or []
    _kv_table(doc, staff_rows, language, dense=True)
    add_signature_grid(
        doc, [text('operator_signature', language), text('head', language), text('director', language)],
        theme=PLAGENOR_THEME,
    )
    p = doc.add_paragraph(text('unsigned', language))
    p.paragraph_format.space_before = Pt(4)
    if legacy:
        add_section_heading(doc, text('legacy', language), theme=PLAGENOR_THEME)
        for key, value in legacy.items():
            p = doc.add_paragraph()
            run = p.add_run(str(key))
            run.bold = True
            doc.add_paragraph(json.dumps(value, ensure_ascii=False, indent=2))
    add_document_footer(doc, theme=PLAGENOR_THEME, reference=metadata['number'])
    _rtl_document(doc, language)
    return doc


def generate_canonical_form(req):
    from django.conf import settings
    from django.utils.translation import get_language
    from core.ibtikar.models import IbtikarSubmission
    from core.ibtikar.schema import (
        active_data, active_names, label, projection, schema_for_service,
    )
    from core.ibtikar.legacy import legacy_initial
    language = (get_language() or 'fr').split('-')[0]
    submission = IbtikarSubmission.objects.filter(request=req).first()
    attachments, signature, legacy = [], None, None
    if submission:
        schema = submission.schema
        project = projection(
            schema, submission.applicant, submission.parameters,
            submission.samples, submission.staff, language,
            print_blank_staff=True,
        )
        active_samples = [
            active_data(schema, 'samples', row, submission.parameters)
            for row in submission.samples
        ]
        active = active_names(
            schema['attachments'], {}, submission.parameters, active_samples,
        )
        for obj in submission.attachments.filter(active=True):
            if obj.field_name not in active:
                continue
            spec = next((field for field in schema['attachments']
                         if field['name'] == obj.field_name), None)
            if not spec:
                continue
            attachments.append({
                'label': label(spec['label'], language),
                'display': obj.original_name,
            })
            if obj.field_name == 'applicant_signature':
                with obj.file.open('rb') as stream:
                    signature = stream.read()
    else:
        schema = schema_for_service(req.service)
        old = legacy_initial(req, schema)
        project = projection(
            schema, old['applicant'], old['parameters'], old['samples'],
            language=language, print_blank_staff=True,
        )
        project['source_version'] = text('unknown', language)
        legacy = old['legacy_data']
    project['staff'] = [
        row for row in project['staff']
        if row['name'] not in ('validated_price', 'price_justification')
    ]
    metadata = {
        'number': req.display_id,
        'date': req.created_at.strftime('%d/%m/%Y'),
        'external_reference': req.ibtikar_external_code,
        'revision': submission.revision if submission else None,
        'draft': req.status == 'DRAFT',
        'operator_name': submission.staff.get('operator_name') if submission else None,
    }
    doc = build_document(project, metadata, language, attachments, signature, legacy)
    from documents.generators import _inject_document_blocks
    _inject_document_blocks(doc, 'IBTIKAR_FORM', req)
    directory = Path(settings.MEDIA_ROOT) / 'documents'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'IBTIKAR_{req.pk}_{uuid.uuid4().hex}.docx'
    doc.save(path)
    return str(path)
