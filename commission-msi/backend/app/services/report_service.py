"""Génération, stockage et export des rapports.

Un export « officiel » exige la porte G7_VALIDATION_HUMAINE. Sans elle, seul un
brouillon filigrané, explicitement non validé, peut être produit.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.core.crypto import sha256_bytes
from app.core.errors import GateBlocked, NotFound, ValidationRefused
from app.core.security import resolve_within
from app.models import Dossier, Report
from app.reports import builder, compact_report, evaluation_report, writers
from app.services import evaluation_service

SUPPORTED_FORMATS = ("docx", "pdf")


#: Deux mises en page possibles. `COMPACT` est le rendu demandé par défaut :
#: trois pages, dense et lisible. `DETAILLE` conserve le rapport complet, utile
#: quand les preuves ou les alertes exigent le détail intégral.
COMPACT = "compact"
DETAILLE = "detaille"
SUPPORTED_LAYOUTS = (COMPACT, DETAILLE)


def generate_report(
    session: Session,
    dossier_id: str,
    *,
    fmt: str,
    official: bool = False,
    layout: str = COMPACT,
) -> Report:
    fmt = (fmt or "").lower().strip()
    if fmt not in SUPPORTED_FORMATS:
        raise ValidationRefused("Format de rapport non pris en charge (docx ou pdf).")
    layout = (layout or COMPACT).lower().strip()
    if layout not in SUPPORTED_LAYOUTS:
        raise ValidationRefused(
            "Mise en page inconnue : « compact » (trois pages) ou « detaille » (rapport complet)."
        )

    dossier = session.get(Dossier, dossier_id)
    if dossier is None:
        raise NotFound("Dossier introuvable.")

    builder_module = compact_report if layout == COMPACT else evaluation_report
    model = builder_module.build(session, dossier_id)

    if official:
        if dossier.report_validated_at is None:
            raise GateBlocked(
                "Export officiel bloqué : la porte G7_VALIDATION_HUMAINE n'est pas satisfaite. "
                "Seul un brouillon filigrané et explicitement non validé peut être produit."
            )
        if model.orphan_facts:
            raise GateBlocked(
                "Export officiel bloqué : le rapport contient des faits sans page ni saisie "
                "manuelle validée (" + ", ".join(model.orphan_facts) + ")."
            )
        findings = evaluation_service.findings_view(session, dossier_id)
        unqualified = builder.unqualified_findings(findings)
        if unqualified:
            raise GateBlocked(
                f"Export officiel bloqué : {len(unqualified)} alerte(s) restent au statut A_VERIFIER."
            )
        model.is_draft = False

    content = writers.write_docx(model) if fmt == "docx" else writers.write_pdf(model)
    digest = sha256_bytes(content)
    pages = _page_count(content) if fmt == "pdf" else None

    settings = get_settings()
    settings.ensure_directories()
    version = (
        int(
            session.scalar(
                select(func.count()).select_from(Report).where(Report.dossier_id == dossier_id)
            )
            or 0
        )
        + 1
    )
    suffix = "officiel" if official else "brouillon"
    filename = f"{dossier.reference}_v{version}_{layout}_{suffix}.{fmt}"
    target = resolve_within(settings.reports_dir, filename)
    target.write_bytes(content)

    report = Report(
        dossier_id=dossier_id,
        fmt=fmt,
        is_draft=not official,
        file_path=str(target),
        sha256=digest,
        version=version,
        evaluator_label=settings.evaluator_label,
    )
    session.add(report)
    audit.record(
        session,
        audit.AuditAction.REPORT_GENERATE,
        f"Rapport {fmt.upper()} v{version} ({suffix}, mise en page {layout}) généré pour "
        f"{dossier.reference}.",
        entity_type="report",
        entity_id=report.id,
        dossier_id=dossier_id,
        fingerprint=f"sha256:{digest}",
    )
    session.commit()
    # Le nombre de pages est mesuré, jamais supposé : c'est un fait vérifiable
    # attaché au fichier réellement produit.
    report.page_count = pages
    return report


def _page_count(pdf_bytes: bytes) -> int | None:
    """Nombre de pages réellement rendues, ou None si la mesure est impossible."""
    try:
        import fitz

        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            return document.page_count
    except Exception:  # noqa: BLE001 - l'absence de mesure ne bloque pas la remise
        return None


def read_report(session: Session, report_id: str) -> tuple[Report, bytes]:
    report = session.get(Report, report_id)
    if report is None:
        raise NotFound("Rapport introuvable.")
    path = Path(report.file_path)
    if not path.exists():
        raise NotFound("Fichier de rapport introuvable sur le disque local.")
    content = path.read_bytes()
    if sha256_bytes(content) != report.sha256:
        raise ValidationRefused(
            "Empreinte du rapport divergente : le fichier a été modifié hors de l'application. "
            "Régénérez le rapport."
        )
    audit.record(
        session,
        audit.AuditAction.REPORT_DOWNLOAD,
        f"Téléchargement du rapport {report.fmt.upper()} v{report.version}.",
        entity_type="report",
        entity_id=report.id,
        dossier_id=report.dossier_id,
    )
    session.commit()
    return report, content


def list_reports(session: Session, dossier_id: str) -> list[Report]:
    return list(
        session.scalars(
            select(Report).where(Report.dossier_id == dossier_id).order_by(Report.created_at.desc())
        ).all()
    )
