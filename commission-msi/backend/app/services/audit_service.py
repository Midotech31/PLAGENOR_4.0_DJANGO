"""Relecture indépendante et règle de consensus (§13 du prompt maître).

L'auditeur ne reçoit **pas** les justifications internes de l'analyste : il ne
voit que les pièces, les données, les preuves et les résultats. Il recalcule
lui-même ce qui est recalculable et compare son résultat à celui enregistré.

La règle de consensus est stricte : tout désaccord non résolu devient `NV`,
avec mention explicite. **Aucune moyenne n'est jamais faite entre deux
réponses** — un chiffre intermédiaire inventé serait une affirmation que
personne n'a produite.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.crypto import decrypt_text
from app.core.keyring import get_master_key
from app.models import AuditDisagreement
from app.models import CriterionResult as CriterionResultRow
from app.models.base import new_id
from app.services import evidence_service, facts_service, regulatory_engine
from app.services.regulatory_engine import Status

#: Mention portée par un critère mis en désaccord.
DISAGREEMENT_NOTE = (
    "Relecture indépendante en désaccord avec la première analyse : le critère est classé "
    "non vérifiable. Aucune moyenne n'est faite entre les deux résultats ; l'arbitrage "
    "revient à l'évaluateur."
)


def _stored_criteria(session: Session, dossier_id: str) -> dict[str, CriterionResultRow]:
    return {
        row.code: row
        for row in session.scalars(
            select(CriterionResultRow).where(CriterionResultRow.dossier_id == dossier_id)
        ).all()
    }


def review(session: Session, dossier_id: str, *, job_id: str | None = None) -> dict:
    """Recalcule les constats à partir des seuls faits et compare aux résultats.

    L'auditeur repart des faits bruts — pièces, valeurs, observations — sans
    connaître le constat rédigé ni le raisonnement suivi.
    """
    facts = facts_service.build_facts(session, dossier_id, rebuild_evidence=False)
    recomputed = {result.code: result for result in regulatory_engine.evaluate(facts)}
    stored = _stored_criteria(session, dossier_id)
    known_evidence = evidence_service.known_references(session, dossier_id)

    disagreements: list[dict] = []
    evidence_problems: list[str] = []

    for code, row in stored.items():
        # Une qualification humaine n'est jamais mise en cause par l'auditeur.
        if row.human_status:
            continue
        audited = recomputed.get(code)
        if audited is None:
            continue
        if audited.status != row.status:
            disagreements.append(
                {
                    "subject": "STATUT_CRITERE",
                    "criterion_code": code,
                    "analyst_value": row.status,
                    "auditor_value": audited.status,
                    "reason": f"La relecture indépendante conclut « {audited.status} » là où la "
                    f"première analyse conclut « {row.status} » sur les mêmes faits.",
                    "evidence_refs": json.loads(row.evidence_refs or "[]"),
                }
            )
        # Contrôle des preuves citées : aucune référence fantôme n'est tolérée.
        cited = json.loads(row.evidence_refs or "[]")
        unknown = [ref for ref in cited if ref not in known_evidence]
        if unknown:
            evidence_problems.append(f"{code} : {', '.join(unknown)}")

    _persist(session, dossier_id, disagreements, job_id=job_id)
    applied = _apply_consensus_rule(session, dossier_id, disagreements)

    audit.record(
        session,
        audit.AuditAction.CRITERION_ASSESS,
        f"Relecture indépendante : {len(stored)} constat(s) recalculé(s), "
        f"{len(disagreements)} désaccord(s), {applied} critère(s) reclassé(s) NV. "
        "Aucune moyenne n'a été faite entre les deux analyses.",
        entity_type="dossier",
        entity_id=dossier_id,
        dossier_id=dossier_id,
    )
    session.commit()

    return {
        "checked": len(stored),
        "disagreements": len(disagreements),
        "reclassified_nv": applied,
        "evidence_problems": evidence_problems,
        "constat": f"{len(stored)} constat(s) relus indépendamment ; {len(disagreements)} "
        f"désaccord(s) non résolu(s) reclassés en « non vérifiable ». "
        + (
            f"{len(evidence_problems)} constat(s) citaient une preuve absente du registre."
            if evidence_problems
            else "Toutes les preuves citées existent au registre."
        ),
    }


def _persist(
    session: Session, dossier_id: str, disagreements: list[dict], *, job_id: str | None
) -> None:
    existing = {
        (row.subject, row.criterion_code): row
        for row in session.scalars(
            select(AuditDisagreement).where(AuditDisagreement.dossier_id == dossier_id)
        ).all()
    }
    seen = set()
    for item in disagreements:
        key = (item["subject"], item["criterion_code"])
        seen.add(key)
        row = existing.get(key)
        if row is None:
            row = AuditDisagreement(
                id=new_id(),
                dossier_id=dossier_id,
                subject=item["subject"],
                criterion_code=item["criterion_code"],
                analyst_value=item["analyst_value"],
                auditor_value=item["auditor_value"],
                reason=item["reason"],
            )
            session.add(row)
        else:
            row.analyst_value = item["analyst_value"]
            row.auditor_value = item["auditor_value"]
            row.reason = item["reason"]
        row.job_id = job_id
        row.evidence_refs = json.dumps(item.get("evidence_refs", []), ensure_ascii=False)

    # Un désaccord disparu est marqué résolu, jamais supprimé de l'historique.
    for key, row in existing.items():
        if key not in seen and not row.resolved:
            row.resolved = True
            row.resolution = "Les deux analyses convergent à nouveau sur les faits courants."
    session.flush()


def _apply_consensus_rule(session: Session, dossier_id: str, disagreements: list[dict]) -> int:
    """Un désaccord non résolu classe le critère `NV`, avec mention explicite."""
    if not disagreements:
        return 0
    stored = _stored_criteria(session, dossier_id)
    applied = 0
    key = get_master_key()
    from app.core.crypto import encrypt_text
    from app.services.assessment_service import criterion_aad

    for item in disagreements:
        row = stored.get(item["criterion_code"])
        if row is None or row.human_status:
            continue
        original = decrypt_text(key, row.finding_cipher, criterion_aad(row.id, "finding")) or ""
        row.status = Status.NV
        row.finding_cipher = encrypt_text(
            key,
            f"{original} {DISAGREEMENT_NOTE} (première analyse : "
            f"{item['analyst_value']} ; relecture : {item['auditor_value']}.)",
            criterion_aad(row.id, "finding"),
        )
        row.note = DISAGREEMENT_NOTE
        applied += 1
    session.flush()
    return applied


def unresolved(session: Session, dossier_id: str) -> list[dict]:
    rows = session.scalars(
        select(AuditDisagreement).where(
            AuditDisagreement.dossier_id == dossier_id, AuditDisagreement.resolved.is_(False)
        )
    ).all()
    return [
        {
            "id": row.id,
            "subject": row.subject,
            "criterion_code": row.criterion_code,
            "analyst_value": row.analyst_value,
            "auditor_value": row.auditor_value,
            "reason": row.reason,
        }
        for row in rows
    ]


def listing(session: Session, dossier_id: str) -> list[dict]:
    rows = session.scalars(
        select(AuditDisagreement)
        .where(AuditDisagreement.dossier_id == dossier_id)
        .order_by(AuditDisagreement.criterion_code)
    ).all()
    return [
        {
            "id": row.id,
            "subject": row.subject,
            "criterion_code": row.criterion_code,
            "analyst_value": row.analyst_value,
            "auditor_value": row.auditor_value,
            "reason": row.reason,
            "resolved": row.resolved,
            "resolution": row.resolution,
            "evidence_ids": json.loads(row.evidence_refs or "[]"),
        }
        for row in rows
    ]
