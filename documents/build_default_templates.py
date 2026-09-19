"""One-shot builder for the four generic DOCX templates.

The originally-shipped ``quote_template.docx`` and
``reception_form_template.docx`` used ``[Service]``-style markers that no
generator ever substituted, leaking raw template syntax into customer-
facing documents. ``platform_note_template.docx`` was worse — a hardcoded
EGTP-Seq02 narrative with no placeholders at all, so every generated
Platform Note showed the same Seq02 text regardless of request.

This module rebuilds the three problem templates with consistent
``{{KEY}}`` placeholders, A4 page size, 1" margins, the institutional
banner in the header, and a discreet generation footer. The IBTIKAR
template is left alone — it already uses ``{{KEY}}`` correctly.

Run via ``python manage.py shell -c "from documents.build_default_templates import build_all; build_all()"``.
The output overwrites ``documents/docx_templates/*.docx``; the originals
are backed up with a ``.bak.docx`` suffix the first time.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from django.conf import settings

from docx import Document
from docx.document import Document as DocumentType
from docx.shared import Pt

from documents.document_design import (
    GENOCLAB_THEME, PLAGENOR_THEME, add_document_footer, add_document_title,
    add_identity_header, add_section_heading, add_signature_grid,
    apply_document_style, style_data_table, style_key_value_table,
)


if __name__ == '__main__':
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')


TEMPLATE_DIR = Path(settings.BASE_DIR) / 'documents' / 'docx_templates'


def _backup(path: Path) -> None:
    if path.exists():
        backup = path.with_suffix('.bak.docx')
        if not backup.exists():
            shutil.copy2(str(path), str(backup))


def _kv_table(doc: DocumentType, rows, *, theme=PLAGENOR_THEME) -> None:
    table = doc.add_table(rows=len(rows), cols=2)
    for i, (label, value) in enumerate(rows):
        table.rows[i].cells[0].text = label
        table.rows[i].cells[1].text = value
    style_key_value_table(table, theme=theme, dense=True)


def build_platform_note_template() -> Path:
    doc = Document()
    apply_document_style(doc, PLAGENOR_THEME, dense=True)
    add_identity_header(doc, PLAGENOR_THEME, compact=True)
    add_document_title(doc, 'NOTE DE PLATEFORME',
                       subtitle='PLAGENOR — synthèse opérationnelle de la demande',
                       code='{{DISPLAY_ID}}', theme=PLAGENOR_THEME)
    add_section_heading(doc, 'Références', theme=PLAGENOR_THEME)
    _kv_table(doc, [('Référence', '{{DISPLAY_ID}}'), ("Date d'émission", '{{DATETIME}}')])

    add_section_heading(doc, 'Demandeur', theme=PLAGENOR_THEME)
    _kv_table(doc, [
        ('Nom complet', '{{FULL_NAME}}'), ('Établissement', '{{ETABLISSEMENT}}'),
        ('Laboratoire', '{{LABORATORY}}'), ('Niveau / fonction', '{{STUDENT_LEVEL}}'),
        ('Directeur de recherche', '{{SUPERVISOR}}'), ('Email', '{{EMAIL}}'),
        ('Téléphone', '{{PHONE}}'),
    ])

    add_section_heading(doc, 'Service demandé', theme=PLAGENOR_THEME)
    _kv_table(doc, [
        ('Code', '{{SERVICE_CODE}}'), ('Intitulé', '{{SERVICE_NAME}}'),
        ('Description', '{{SERVICE_DESCRIPTION}}'), ('Délai (jours ouvrables)', '{{SERVICE_TURNAROUND}}'),
        ('Canal', '{{CHANNEL}}'), ('Urgence', '{{URGENCY}}'),
    ])

    add_section_heading(doc, 'Détails de la demande', theme=PLAGENOR_THEME)
    _kv_table(doc, [
        ('Titre', '{{TITLE}}'), ('Description', '{{DESCRIPTION}}'),
        ('Paramètres', '{{SERVICE_PARAMS}}'), ('Échantillons', '{{SAMPLE_SUMMARY}}'),
    ])
    add_section_heading(doc, 'Décompte budgétaire IBTIKAR', theme=PLAGENOR_THEME)
    _kv_table(doc, [
        ('Budget annuel par étudiant', '200 000 DA'),
        ('Montant de cette prestation', '{{BUDGET_AMOUNT}}'),
        ('Solde IBTIKAR déclaré', '{{IBTIKAR_BALANCE}}'),
    ])
    add_section_heading(doc, 'Assignation', theme=PLAGENOR_THEME)
    _kv_table(doc, [
        ('Analyste', '{{ASSIGNED_ANALYST}}'), ('Email analyste', '{{ANALYST_EMAIL}}'),
        ('Rendez-vous', '{{APPOINTMENT_DATE}}'),
    ])
    add_document_footer(doc, theme=PLAGENOR_THEME, reference='{{DISPLAY_ID}}')
    path = TEMPLATE_DIR / 'platform_note_template.docx'
    _backup(path); doc.save(str(path)); return path


def build_quote_template() -> Path:
    doc = Document()
    apply_document_style(doc, GENOCLAB_THEME, dense=True)
    add_identity_header(doc, GENOCLAB_THEME, compact=True)
    add_document_title(doc, 'DEVIS', subtitle='GENOCLAB — prestations scientifiques et technologiques',
                       code='{{QUOTE_NUMBER}}', theme=GENOCLAB_THEME)
    add_section_heading(doc, 'Document et client', theme=GENOCLAB_THEME)
    _kv_table(doc, [
        ('Date', '{{DATE}}'), ('N°', '{{QUOTE_NUMBER}}'),
        ('Référence demande', '{{DISPLAY_ID}}'), ('Client', '{{CLIENT_NAME}}'),
        ('Organisation', '{{ORGANIZATION}}'), ('Laboratoire', '{{LABORATORY}}'),
        ('Tél.', '{{PHONE}}'), ('Email', '{{CLIENT_EMAIL}}'),
    ], theme=GENOCLAB_THEME)
    add_section_heading(doc, 'Prestations', theme=GENOCLAB_THEME)
    table=doc.add_table(rows=2,cols=4)
    for j,h in enumerate(['Prestation','Quantité','Prix unitaire DA','Montant DA']):
        table.rows[0].cells[j].text=h
    table.rows[1].cells[0].text='{{SERVICE_NAME}}'
    table.rows[1].cells[1].text='1'
    table.rows[1].cells[2].text='{{SUBTOTAL_HT}}'
    table.rows[1].cells[3].text='{{SUBTOTAL_HT}}'
    style_data_table(table,theme=GENOCLAB_THEME,dense=True,numeric_cols=(1,2,3))
    summary=doc.add_table(rows=3,cols=2)
    for row,(label,value) in zip(summary.rows,[
        ('Sous-total HT','{{SUBTOTAL_HT}}'),('TVA ({{VAT_RATE}})','{{VAT_AMOUNT}}'),
        ('Total TTC','{{TOTAL_TTC}}')]):
        row.cells[0].text,row.cells[1].text=label,value
    style_key_value_table(summary,theme=GENOCLAB_THEME,dense=True)
    add_document_footer(doc,theme=GENOCLAB_THEME,reference='{{DISPLAY_ID}}')
    path=TEMPLATE_DIR/'quote_template.docx'
    _backup(path); doc.save(str(path)); return path


def build_reception_form_template() -> Path:
    doc=Document()
    apply_document_style(doc,PLAGENOR_THEME,dense=True)
    add_identity_header(doc,PLAGENOR_THEME,compact=True)
    add_document_title(doc,"FICHE DE RÉCEPTION D'ÉCHANTILLONS",
                       subtitle='Traçabilité de la remise et du contrôle initial',
                       code='{{DISPLAY_ID}}',theme=PLAGENOR_THEME)
    add_section_heading(doc,'Références de la demande',theme=PLAGENOR_THEME)
    _kv_table(doc,[
        ('Service','{{SERVICE_NAME}}'),('Canal','{{CHANNEL}}'),('Urgence','{{URGENCY}}'),
        ('Date de RDV','{{APPOINTMENT_DATE}}'),('Analyste assigné','{{ASSIGNED_ANALYST}}'),
        ('Date de soumission','{{SUBMISSION_DATE}}')])
    add_section_heading(doc,'Déposant',theme=PLAGENOR_THEME)
    _kv_table(doc,[
        ('Nom','{{FULL_NAME}}'),('Email','{{EMAIL}}'),('Téléphone','{{PHONE}}'),
        ('Établissement','{{ETABLISSEMENT}}'),('Laboratoire','{{LABORATORY}}')])
    add_section_heading(doc,'Échantillons soumis',theme=PLAGENOR_THEME)
    doc.add_paragraph('{{SAMPLE_TABLE}}')
    add_section_heading(doc,'Contrôle à la réception',theme=PLAGENOR_THEME)
    _kv_table(doc,[
        ('Date de réception','___ / ___ / ______'),
        ("Nombre d'échantillons reçus",'____________'),
        ('État des échantillons','☐ Bon   ☐ Acceptable   ☐ Dégradé'),
        ('Observations','')])
    add_signature_grid(doc,['Signature du réceptionniste','Signature du déposant'],theme=PLAGENOR_THEME)
    add_document_footer(doc,theme=PLAGENOR_THEME,reference='{{DISPLAY_ID}}')
    path=TEMPLATE_DIR/'reception_form_template.docx'
    _backup(path); doc.save(str(path)); return path


def _add_footer(doc: DocumentType) -> None:
    add_document_footer(doc, theme=PLAGENOR_THEME)


def build_all():
    """Build all three programmatic templates. Returns the list of paths."""
    return [
        build_platform_note_template(),
        build_quote_template(),
        build_reception_form_template(),
    ]


if __name__ == '__main__':
    import django
    django.setup()
    for p in build_all():
        print(f'wrote {p}')
