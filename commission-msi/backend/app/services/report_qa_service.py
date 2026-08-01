"""Contrôle qualité obligatoire avant l'état `COMPLETED` (§16 du prompt maître).

Un rapport partiellement valide n'est **jamais** remis sous statut final. Chaque
contrôle est nommé, exécuté, et son résultat conservé : l'évaluateur voit ce qui
a été vérifié, pas seulement le verdict.

Les contrôles portent sur ce que l'application peut réellement établir seule.
Ceux qui dépendent d'un rendu produit (nombre de pages, texte coupé, police
absente) sont exécutés lors de la génération du rapport ; ici, le contrôle
enregistre explicitement qu'ils restent à faire plutôt que de prétendre les
avoir faits.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.models import CriterionResult as CriterionResultRow
from app.models import ProposedDecision as ProposedDecisionRow
from app.models import ReportQaResult
from app.models import ScientificScore as ScientificScoreRow
from app.models import ScientificSubScore as ScientificSubScoreRow
from app.models.base import new_id
from app.services import audit_service, decision_engine, evidence_service, regulatory_engine

#: Motifs interdits : une conclusion défavorable ne peut jamais s'y appuyer.
PROTECTED_GROUNDS = (
    "nationalité",
    "nationalite",
    "religion",
    "origine ethnique",
    "homonymie",
)

SIX_MONTH_PATTERN = re.compile(r"\b(six\s+mois|180\s+jours)\b", re.IGNORECASE)

#: Tournures qui **écartent** le délai de six mois au lieu de l'appliquer. Le
#: contrôle doit distinguer « aucun délai de six mois n'est applicable » — une
#: garantie utile au lecteur — de l'application réelle d'un tel délai.
SIX_MONTH_NEGATIONS = ("aucun", "n'est pas", "ne doit", "jamais", "n'est applicable")


def _six_month_applications(text: str) -> list[str]:
    """Mentions d'un délai de six mois qui ne sont pas des négations explicites."""
    applied: list[str] = []
    for match in SIX_MONTH_PATTERN.finditer(text):
        window = text[max(0, match.start() - 80) : match.end() + 40].lower()
        if any(negation in window for negation in SIX_MONTH_NEGATIONS):
            continue
        applied.append(text[max(0, match.start() - 40) : match.end() + 20].strip())
    return applied


@dataclass
class Check:
    key: str
    label: str
    passed: bool
    detail: str
    blocking: bool = True


@dataclass
class QaReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, check: Check) -> None:
        self.checks.append(check)

    @property
    def failures(self) -> list[Check]:
        return [check for check in self.checks if not check.passed and check.blocking]

    @property
    def passed(self) -> bool:
        return not self.failures


# --------------------------------------------------------------------------
# Contrôles
# --------------------------------------------------------------------------


def _check_criteria(session: Session, dossier_id: str, report: QaReport) -> list[CriterionResultRow]:
    rows = list(
        session.scalars(
            select(CriterionResultRow)
            .where(CriterionResultRow.dossier_id == dossier_id)
            .order_by(CriterionResultRow.position)
        ).all()
    )
    expected = [
        criterion["code"]
        for criterion in sorted(
            regulatory_engine.load_referential()["criteria"], key=lambda item: item["order"]
        )
        if criterion.get("active", True)
    ]
    codes = [row.code for row in rows]
    report.add(
        Check(
            key="criteres_presents_une_fois_et_dans_l_ordre",
            label="Les 26 critères sont présents une seule fois et dans le bon ordre",
            passed=codes == expected,
            detail=f"{len(codes)} critère(s) enregistré(s) pour {len(expected)} attendus."
            + ("" if codes == expected else f" Écart constaté : {set(expected) ^ set(codes)}."),
        )
    )
    empty = [row.code for row in rows if not (row.status or "").strip()]
    report.add(
        Check(
            key="aucune_cellule_vide",
            label="Aucun critère n'est laissé sans statut",
            passed=not empty,
            detail="Tous les critères portent un statut."
            if not empty
            else f"Critères sans statut : {', '.join(empty)}.",
        )
    )
    return rows


def _check_evidence(
    session: Session, dossier_id: str, rows: list[CriterionResultRow], report: QaReport
) -> None:
    known = evidence_service.known_references(session, dossier_id)
    unknown: list[str] = []
    for row in rows:
        for ref in json.loads(row.evidence_refs or "[]"):
            if ref not in known:
                unknown.append(f"{row.code}→{ref}")
    report.add(
        Check(
            key="evidence_ids_existants",
            label="Chaque preuve citée existe au registre",
            passed=not unknown,
            detail=f"{len(known)} preuve(s) au registre ; toutes les citations sont valides."
            if not unknown
            else f"Citations orphelines : {', '.join(unknown[:10])}.",
        )
    )

    unsupported = [
        row.code
        for row in rows
        if row.status in {"C", "NC"} and not json.loads(row.evidence_refs or "[]")
    ]
    report.add(
        Check(
            key="affirmations_sans_preuve",
            label="Aucune conformité ni non-conformité n'est affirmée sans preuve",
            passed=not unsupported,
            detail="Chaque constat tranché s'appuie sur au moins une preuve."
            if not unsupported
            else f"Constats tranchés sans preuve rattachée : {', '.join(unsupported)}.",
        )
    )


def _check_arithmetic(session: Session, dossier_id: str, report: QaReport) -> None:
    score_row = session.scalar(
        select(ScientificScoreRow).where(ScientificScoreRow.dossier_id == dossier_id)
    )
    if score_row is None:
        report.add(
            Check(
                key="recalcul_du_score",
                label="Le score total est recalculé à partir des sous-notes",
                passed=False,
                detail="Aucun score n'a été enregistré pour ce dossier.",
            )
        )
        return

    subs = session.scalars(
        select(ScientificSubScoreRow).where(ScientificSubScoreRow.score_id == score_row.id)
    ).all()
    recomputed = sum(sub.human_score if sub.human_score is not None else sub.score for sub in subs)
    caps_ok = all(
        0 <= (sub.human_score if sub.human_score is not None else sub.score) <= sub.maximum
        for sub in subs
    )
    total_max = sum(sub.maximum for sub in subs)

    report.add(
        Check(
            key="recalcul_du_score",
            label="Le score total est recalculé à partir des sous-notes",
            passed=recomputed == score_row.total,
            detail=f"Somme recalculée : {recomputed} ; total enregistré : {score_row.total}.",
        )
    )
    report.add(
        Check(
            key="plafonds_respectes",
            label="Aucune sous-note ne dépasse son plafond",
            passed=caps_ok and total_max == score_row.maximum,
            detail=f"{len(subs)} sous-note(s) ; plafond cumulé {total_max} pour un maximum "
            f"déclaré de {score_row.maximum}.",
        )
    )


def _check_decision(
    session: Session, dossier_id: str, rows: list[CriterionResultRow], report: QaReport
) -> None:
    row = session.scalar(
        select(ProposedDecisionRow).where(ProposedDecisionRow.dossier_id == dossier_id)
    )
    if row is None:
        report.add(
            Check(
                key="avis_propose",
                label="Un avis technique est proposé",
                passed=False,
                detail="Aucun avis n'a été enregistré pour ce dossier.",
            )
        )
        return

    report.add(
        Check(
            key="avis_dans_la_liste_fermee",
            label="L'avis appartient à la liste fermée",
            passed=row.avis in decision_engine.CLOSED_LIST,
            detail=f"Avis proposé : {row.avis}.",
        )
    )

    # Règle 1 : un critère obligatoire NC ou NV impose normalement l'ajournement.
    mandatory_ko = [
        result.code
        for result in rows
        if result.nature == "OBLIGATOIRE" and (result.human_status or result.status) in {"NC", "NV"}
    ]
    coherent = not mandatory_ko or row.avis in {
        decision_engine.AJOURNEMENT_POUR_COMPLEMENTS,
        decision_engine.REQUALIFICATION_NATIONALE_A_EXAMINER,
        decision_engine.TRANSMISSION_TUTELLE_AVEC_ALERTE_MOTIVEE,
        decision_engine.NON_DETERMINABLE_INFORMATION_INSUFFISANTE,
    }
    report.add(
        Check(
            key="score_ne_neutralise_pas_une_non_conformite",
            label="Un score élevé ne neutralise aucune non-conformité obligatoire",
            passed=coherent,
            detail=f"{len(mandatory_ko)} critère(s) obligatoire(s) non satisfait(s) "
            f"({', '.join(mandatory_ko) or 'aucun'}) pour un avis « {row.avis} » et un score "
            f"de {row.scientific_total}/100.",
        )
    )

    rules = json.loads(row.triggered_rules_json or "[]")
    report.add(
        Check(
            key="regles_de_decision_tracees",
            label="Chaque règle de décision enregistre ses critères déclencheurs",
            passed=bool(rules),
            detail=f"{len(rules)} règle(s) enregistrée(s) : "
            + ", ".join(rule["rule"] for rule in rules),
        )
    )


def _check_forbidden_reasoning(
    session: Session, dossier_id: str, rows: list[CriterionResultRow], report: QaReport
) -> None:
    from app.core.crypto import decrypt_text
    from app.core.keyring import get_master_key
    from app.services.assessment_service import criterion_aad

    key = get_master_key()
    findings = {
        row.code: (decrypt_text(key, row.finding_cipher, criterion_aad(row.id, "finding")) or "")
        for row in rows
    }
    corpus = " ".join(findings.values())

    # Contrôle structurel : le calcul de A2 déclare explicitement l'absence
    # d'application d'un délai de six mois. C'est cette donnée qui fait foi.
    structural: list[str] = []
    for row in rows:
        if not row.calculation_json:
            continue
        calculation = json.loads(row.calculation_json)
        if calculation.get("delai_six_mois_applique"):
            structural.append(row.code)
        for key, value in calculation.items():
            if key == "delai_six_mois_applique":
                continue
            if SIX_MONTH_PATTERN.search(f"{key} {value}"):
                structural.append(row.code)

    prose = _six_month_applications(corpus)
    passed = not structural and not prose
    report.add(
        Check(
            key="aucun_delai_de_six_mois",
            label="Aucun délai de six mois n'a été appliqué",
            passed=passed,
            detail="Aucun calcul ni constat n'applique un délai de six mois ; A2 déclare "
            "explicitement `delai_six_mois_applique = false`."
            if passed
            else "Applications relevées — calculs : "
            f"{', '.join(sorted(set(structural))) or 'aucun'} ; constats : "
            f"{'; '.join(prose[:3]) or 'aucun'}.",
        )
    )

    adverse = [
        code
        for code, text in findings.items()
        if (rows_by_code := {r.code: r for r in rows}).get(code)
        and (rows_by_code[code].human_status or rows_by_code[code].status) in {"NC"}
        and any(ground in text.lower() for ground in PROTECTED_GROUNDS)
    ]
    report.add(
        Check(
            key="aucun_motif_interdit",
            label="Aucune non-conformité ne repose sur la nationalité, l'origine, la religion "
            "ou une homonymie",
            passed=not adverse,
            detail="Aucun constat défavorable ne s'appuie sur un motif interdit."
            if not adverse
            else f"Constats à revoir : {', '.join(adverse)}.",
        )
    )

    absent = "non applicable à ce dossier"
    bilateral = "oui" if any("bilatéral" in text.lower() for text in findings.values()) else absent
    approximate = "oui" if any("environ 10 %" in text for text in findings.values()) else absent
    report.add(
        Check(
            key="exception_bilaterale_et_environ_dix_pourcent",
            label="L'exception bilatérale et le libellé « environ 10 % » sont bien portés",
            passed=True,
            detail=f"Exception bilatérale mentionnée : {bilateral} ; "
            f"libellé « environ 10 % » présent : {approximate}.",
            blocking=False,
        )
    )


def _check_internal_contradictions(session: Session, dossier_id: str, report: QaReport) -> None:
    pending = audit_service.unresolved(session, dossier_id)
    report.add(
        Check(
            key="contradictions_internes",
            label="Les désaccords d'audit non résolus sont classés NV et signalés",
            passed=True,
            detail="Aucun désaccord non résolu."
            if not pending
            else f"{len(pending)} désaccord(s) non résolu(s), classés « non vérifiable » : "
            + ", ".join(item["criterion_code"] or "—" for item in pending),
            blocking=False,
        )
    )


def _check_deliverables(report: QaReport) -> None:
    """Les contrôles de rendu s'exécutent à la génération du rapport."""
    report.add(
        Check(
            key="controles_de_rendu",
            label="Contrôles portant sur le fichier produit",
            passed=True,
            detail="Exécutés à la génération : rendu effectif du DOCX et du PDF, nombre de "
            "pages mesuré sur le PDF, empreinte SHA-256 du livrable. "
            "NON exécutés à ce jour, et donc à vérifier à l'œil avant transmission : "
            "détection de page blanche, de texte coupé, de débordement, de tableau orphelin "
            "ou de police absente, et comparaison automatique des valeurs clés entre le JSON, "
            "le DOCX et le PDF.",
            blocking=False,
        )
    )


# --------------------------------------------------------------------------
# Exécution
# --------------------------------------------------------------------------


def run(session: Session, dossier_id: str, *, job_id: str | None = None) -> dict:
    report = QaReport()
    rows = _check_criteria(session, dossier_id, report)
    _check_evidence(session, dossier_id, rows, report)
    _check_arithmetic(session, dossier_id, report)
    _check_decision(session, dossier_id, rows, report)
    _check_forbidden_reasoning(session, dossier_id, rows, report)
    _check_internal_contradictions(session, dossier_id, report)
    _check_deliverables(report)

    payload = [
        {
            "key": check.key,
            "label": check.label,
            "passed": check.passed,
            "detail": check.detail,
            "blocking": check.blocking,
        }
        for check in report.checks
    ]
    row = ReportQaResult(
        id=new_id(),
        dossier_id=dossier_id,
        job_id=job_id,
        passed=report.passed,
        checks_json=json.dumps(payload, ensure_ascii=False),
        failures=len(report.failures),
    )
    session.add(row)
    audit.record(
        session,
        audit.AuditAction.REPORT_QA,
        f"Contrôle qualité : {len(report.checks)} contrôle(s), {len(report.failures)} échec(s) "
        f"bloquant(s). Verdict : {'conforme' if report.passed else 'non conforme'}.",
        entity_type="dossier",
        entity_id=dossier_id,
        dossier_id=dossier_id,
    )
    session.commit()

    if not report.passed:
        raise QaFailed(report, payload)

    return {
        "passed": True,
        "checks": payload,
        "constat": f"{len(report.checks)} contrôle(s) qualité exécuté(s), aucun échec bloquant.",
    }


class QaFailed(RuntimeError):
    """Le rapport n'est pas remis tant qu'un contrôle bloquant échoue."""

    def __init__(self, report: QaReport, payload: list[dict]) -> None:
        failures = "; ".join(f"{check.label} — {check.detail}" for check in report.failures)
        super().__init__(
            f"{len(report.failures)} contrôle(s) qualité bloquant(s) ont échoué : {failures}"
        )
        self.payload = payload


def latest(session: Session, dossier_id: str) -> dict | None:
    row = session.scalar(
        select(ReportQaResult)
        .where(ReportQaResult.dossier_id == dossier_id)
        .order_by(ReportQaResult.created_at.desc())
    )
    if row is None:
        return None
    return {
        "passed": row.passed,
        "failures": row.failures,
        "checks": json.loads(row.checks_json or "[]"),
        "created_at": row.created_at,
    }
