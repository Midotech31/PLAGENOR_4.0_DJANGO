"""Écriture du rapport en DOCX (python-docx) et PDF (ReportLab), hors ligne."""

from __future__ import annotations

from io import BytesIO

from app.core.config import DRAFT_BANNER, SIGNATURE
from app.reports.builder import PERSONAL_PROPOSAL_NOTICE, ReportModel

#: Préfixe visuel distinguant la nature de chaque contenu.
KIND_PREFIX = {
    "FAIT_EXTRAIT": "[FAIT EXTRAIT]",
    "CALCUL": "[CALCUL]",
    "ALERTE_SYSTEME": "[ALERTE SYSTÈME]",
    "COMMENTAIRE_EVALUATEUR": "[COMMENTAIRE ÉVALUATEUR]",
    "CONCLUSION_EVALUATEUR": "[CONCLUSION ÉVALUATEUR]",
    "A_VERIFIER": "[À VÉRIFIER]",
}


def _line_text(line) -> str:
    prefix = KIND_PREFIX.get(line.kind, f"[{line.kind}]")
    return f"{prefix} {line.text} — source : {line.source_label}"


def write_docx(model: ReportModel) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    document = Document()
    document.core_properties.title = f"Rapport — {model.dossier_reference}"
    document.core_properties.author = model.evaluator

    banner = document.add_paragraph()
    banner.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = banner.add_run(DRAFT_BANNER)
    run.bold = True
    run.font.size = Pt(14)

    if model.is_draft:
        warning = document.add_paragraph()
        warning.alignment = WD_ALIGN_PARAGRAPH.CENTER
        warning_run = warning.add_run(
            "BROUILLON NON VALIDÉ — la porte G7_VALIDATION_HUMAINE n'est pas satisfaite. "
            "Ce document ne peut pas être utilisé comme rapport officiel."
        )
        warning_run.italic = True

    document.add_heading(f"Dossier {model.dossier_reference}", level=1)
    document.add_paragraph(f"Intitulé : {model.dossier_title}")
    document.add_paragraph(f"Organisateur : {model.organizer}")
    document.add_paragraph(f"Évaluateur : {model.evaluator}")
    document.add_paragraph(
        f"Généré le {model.generated_at.strftime('%Y-%m-%d %H:%M UTC')} — version {model.version}"
    )
    document.add_paragraph(PERSONAL_PROPOSAL_NOTICE)

    for section in model.sections:
        document.add_heading(f"{section.number}. {section.title}", level=2)
        for line in section.lines:
            document.add_paragraph(_line_text(line), style="List Bullet")

    document.add_paragraph()
    signature = document.add_paragraph()
    signature.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    signature_run = signature.add_run(SIGNATURE)
    signature_run.italic = True

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def write_pdf(model: ReportModel) -> bytes:
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=f"Rapport — {model.dossier_reference}",
        author=model.evaluator,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    banner_style = ParagraphStyle(
        "Banner", parent=styles["Title"], fontSize=14, alignment=TA_CENTER, spaceAfter=8
    )
    signature_style = ParagraphStyle(
        "Signature", parent=styles["Normal"], alignment=TA_RIGHT, fontName="Helvetica-Oblique"
    )
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, leading=12)

    story = [Paragraph(_escape(DRAFT_BANNER), banner_style)]
    if model.is_draft:
        story.append(
            Paragraph(
                _escape(
                    "BROUILLON NON VALIDÉ — la porte G7_VALIDATION_HUMAINE n'est pas satisfaite. "
                    "Ce document ne peut pas être utilisé comme rapport officiel."
                ),
                body_style,
            )
        )
    story.extend(
        [
            Spacer(1, 6),
            Paragraph(_escape(f"Dossier {model.dossier_reference}"), styles["Heading1"]),
            Paragraph(_escape(f"Intitulé : {model.dossier_title}"), body_style),
            Paragraph(_escape(f"Organisateur : {model.organizer}"), body_style),
            Paragraph(_escape(f"Évaluateur : {model.evaluator}"), body_style),
            Paragraph(
                _escape(
                    f"Généré le {model.generated_at.strftime('%Y-%m-%d %H:%M UTC')} — version {model.version}"
                ),
                body_style,
            ),
            Paragraph(_escape(PERSONAL_PROPOSAL_NOTICE), body_style),
            Spacer(1, 8),
        ]
    )

    for section in model.sections:
        story.append(Paragraph(_escape(f"{section.number}. {section.title}"), styles["Heading2"]))
        for line in section.lines:
            story.append(Paragraph(_escape(_line_text(line)), body_style))
        story.append(Spacer(1, 6))

    story.append(PageBreak())
    story.append(Paragraph(_escape(SIGNATURE), signature_style))

    def _watermark(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(18 * mm, 10 * mm, DRAFT_BANNER)
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, SIGNATURE)
        if model.is_draft:
            canvas.setFont("Helvetica-Bold", 48)
            canvas.setFillGray(0.85)
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "BROUILLON")
        canvas.restoreState()

    document.build(story, onFirstPage=_watermark, onLaterPages=_watermark)
    return buffer.getvalue()


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
