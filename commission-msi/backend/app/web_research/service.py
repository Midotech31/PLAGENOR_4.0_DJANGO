"""Cycle de vie d'une campagne de recherche publique contrôlée.

Étapes : préparation des requêtes → relecture et modification humaine →
approbation → exécution → collecte des sources → agents → ranking indicatif.

Rien ne part du poste sans une requête minimale explicitement approuvée.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import AgentInput
from app.agents.orchestrator import orchestrate
from app.core import audit
from app.core.config import get_settings
from app.core.crypto import decrypt_text, encrypt_text, sha256_bytes, value_fingerprint
from app.core.errors import NotFound, ValidationRefused
from app.core.keyring import get_master_key
from app.core.vocabulary import (
    WEB_UNAVAILABLE_MESSAGE,
    ClaimNature,
    DossierStatus,
    EvidenceStatus,
    InformationStatus,
    WebRunStatus,
)
from app.models import (
    AgentAssessment,
    Dossier,
    ExtractedItem,
    IdentityDisambiguation,
    OnlineClaim,
    PersonWebProfile,
    Regulation,
    WebQuery,
    WebResearchRun,
    WebSource,
)
from app.ranking import service as ranking_service
from app.web_research import egress, providers, redaction

#: Informations du dossier qui peuvent alimenter une requête publique.
PUBLIC_SUBJECT_KEYS: dict[str, str] = {
    "intitule": "MANIFESTATION",
    "etablissement_organisateur": "INSTITUTION",
    "structure_porteuse": "INSTITUTION",
    "responsable_scientifique": "PERSONNE",
    "comite_scientifique": "PERSONNE",
    "comite_organisation": "PERSONNE",
    "intervenants": "PERSONNE",
    "institutions_representees": "INSTITUTION",
    "partenaires": "PARTENAIRE",
    "sponsors": "SPONSOR",
    "financeurs": "FINANCEUR",
}

MAX_QUERIES_PER_RUN = 60


def claim_aad(claim_id: str, field: str) -> str:
    return f"claim:{claim_id}:{field}"


def source_aad(source_id: str) -> str:
    return f"web_source:{source_id}:excerpt"


# --------------------------------------------------------------------------
# Connectivité et état
# --------------------------------------------------------------------------


def connectivity(session: Session | None = None) -> dict:
    state = providers.check_connectivity()
    payload = {
        **state,
        "providers": providers.provider_states(),
        "egress": egress.policy_state(),
        "message": (
            "Connectivité disponible pour la recherche publique contrôlée."
            if state["online"]
            else WEB_UNAVAILABLE_MESSAGE
        ),
    }
    if session is not None:
        audit.record(
            session,
            audit.AuditAction.WEB_CONNECTIVITY_CHECK,
            f"Vérification de connectivité : {'en ligne' if state['online'] else 'hors ligne'} "
            f"({state['reason']}).",
        )
        session.commit()
    return payload


# --------------------------------------------------------------------------
# Préparation
# --------------------------------------------------------------------------


def prepare_run(session: Session, dossier_id: str, *, scope_note: str = "") -> WebResearchRun:
    """Construit les requêtes candidates à partir des seules informations publiques.

    Aucune requête n'est envoyée à cette étape : l'évaluateur doit les relire.
    """
    dossier = session.get(Dossier, dossier_id)
    if dossier is None:
        raise NotFound("Dossier introuvable.")

    state = providers.check_connectivity()
    run = WebResearchRun(
        dossier_id=dossier_id,
        status=WebRunStatus.PREPAREE,
        scope_note=scope_note.strip(),
        connectivity_ok=bool(state["online"]),
        providers_json=json.dumps(
            [provider.name for provider in providers.enabled_providers()], ensure_ascii=False
        ),
    )
    session.add(run)
    session.flush()

    key = get_master_key()
    items = session.scalars(
        select(ExtractedItem).where(
            ExtractedItem.dossier_id == dossier_id,
            ExtractedItem.key.in_(tuple(PUBLIC_SUBJECT_KEYS)),
        )
    ).all()

    prepared = 0
    for item in items:
        if item.status in {InformationStatus.REJETE, InformationStatus.NON_APPLICABLE}:
            continue
        value = decrypt_text(key, item.current_value_cipher, f"item:{item.id}:current")
        if not value or not value.strip():
            continue
        subject_kind = PUBLIC_SUBJECT_KEYS[item.key]
        for label in _split_subjects(value):
            if prepared >= MAX_QUERIES_PER_RUN:
                break
            query_text = _build_query(label, subject_kind, dossier)
            report = _preflight(query_text, subject_kind)
            session.add(
                WebQuery(
                    run_id=run.id,
                    subject_kind=subject_kind,
                    subject_label=label,
                    query_text=query_text,
                    purpose=f"Vérification publique du champ « {item.label} ».",
                    approved=False,
                    redaction_report_json=json.dumps(report, ensure_ascii=False),
                )
            )
            prepared += 1

    if prepared == 0:
        query_text = _build_query(dossier.title, "MANIFESTATION", dossier)
        session.add(
            WebQuery(
                run_id=run.id,
                subject_kind="MANIFESTATION",
                subject_label=dossier.title,
                query_text=query_text,
                purpose="Vérification publique de l'intitulé de la manifestation.",
                approved=False,
                redaction_report_json=json.dumps(
                    _preflight(query_text, "MANIFESTATION"), ensure_ascii=False
                ),
            )
        )
        prepared = 1

    dossier.status = DossierStatus.RECHERCHE_WEB_REQUISE
    audit.record(
        session,
        audit.AuditAction.WEB_RUN_PREPARE,
        f"Campagne de recherche préparée : {prepared} requête(s) candidates, "
        f"connectivité {'disponible' if state['online'] else 'indisponible'}.",
        entity_type="web_research_run",
        entity_id=run.id,
        dossier_id=dossier_id,
    )
    session.commit()
    return run


def _split_subjects(value: str) -> list[str]:
    parts = [part.strip() for chunk in value.split(";") for part in chunk.split(",")]
    return [part for part in parts if len(part) >= 3][:8]


def _build_query(label: str, subject_kind: str, dossier: Dossier) -> str:
    if subject_kind == "MANIFESTATION":
        return label.strip()[: redaction.MAX_QUERY_LENGTH]
    return f"{label.strip()} {dossier.organizer.strip()}"[: redaction.MAX_QUERY_LENGTH]


def _preflight(query_text: str, subject_kind: str) -> dict:
    """Contrôle de redaction en amont, sans lever d'exception."""
    try:
        return redaction.assert_sendable(query_text, subject_kind=subject_kind)
    except redaction.PayloadRefused as exc:
        return {"verdict": "REFUSEE", "reason": exc.message}


def edit_query(session: Session, query_id: str, *, query_text: str, approved: bool) -> WebQuery:
    """L'évaluateur relit et modifie chaque requête avant tout envoi."""
    query = session.get(WebQuery, query_id)
    if query is None:
        raise NotFound("Requête introuvable.")
    text = (query_text or "").strip()
    report = redaction.assert_sendable(text, subject_kind=query.subject_kind)
    query.query_text = text
    query.approved = approved
    query.approved_by = get_settings().evaluator_label if approved else None
    query.redaction_report_json = json.dumps(report, ensure_ascii=False)
    audit.record(
        session,
        audit.AuditAction.WEB_QUERY_EDIT,
        f"Requête « {query.subject_label} » relue par l'évaluateur "
        f"({'approuvée' if approved else 'non approuvée'}).",
        entity_type="web_query",
        entity_id=query.id,
        fingerprint=value_fingerprint(text),
    )
    session.commit()
    return query


def approve_run(session: Session, run_id: str, *, approved_by: str) -> WebResearchRun:
    run = _get_run(session, run_id)
    approved = [query for query in run.queries if query.approved]
    if not approved:
        raise ValidationRefused(
            "Aucune requête approuvée : rien ne peut quitter le poste. Relisez et approuvez "
            "au moins une requête minimale."
        )
    run.approved_by = approved_by
    run.approved_at = datetime.now(timezone.utc)
    audit.record(
        session,
        audit.AuditAction.WEB_RUN_APPROVE,
        f"Campagne approuvée par {approved_by} : {len(approved)} requête(s) autorisée(s).",
        entity_type="web_research_run",
        entity_id=run.id,
        dossier_id=run.dossier_id,
    )
    session.commit()
    return run


# --------------------------------------------------------------------------
# Exécution
# --------------------------------------------------------------------------


def execute_run(session: Session, run_id: str) -> dict:
    """Exécute les requêtes approuvées, collecte les sources, lance les agents."""
    run = _get_run(session, run_id)
    if run.approved_at is None:
        raise ValidationRefused("Campagne non approuvée : aucune requête ne peut être envoyée.")
    if run.status in {WebRunStatus.ANNULEE, WebRunStatus.ECARTEE_PAR_HUMAIN}:
        raise ValidationRefused("Campagne annulée ou écartée : relancez une nouvelle préparation.")

    state = providers.check_connectivity()
    dossier = session.get(Dossier, run.dossier_id)
    if not state["online"]:
        run.status = WebRunStatus.ECHOUEE
        run.connectivity_ok = False
        run.failure_reason = WEB_UNAVAILABLE_MESSAGE
        run.finished_at = datetime.now(timezone.utc)
        audit.record(
            session,
            audit.AuditAction.WEB_PROVIDER_ERROR,
            f"Campagne interrompue : {state['reason']}",
            entity_type="web_research_run",
            entity_id=run.id,
            dossier_id=run.dossier_id,
        )
        session.commit()
        return {
            "run_id": run.id,
            "status": run.status,
            "online": False,
            "message": WEB_UNAVAILABLE_MESSAGE,
            "sources": 0,
            "claims": 0,
        }

    run.status = WebRunStatus.EN_COURS
    run.connectivity_ok = True
    run.started_at = datetime.now(timezone.utc)
    if dossier is not None:
        dossier.status = DossierStatus.RECHERCHE_WEB_EN_COURS
    audit.record(
        session,
        audit.AuditAction.WEB_RUN_START,
        f"Démarrage de la campagne de recherche publique ({len(run.queries)} requête(s)).",
        entity_type="web_research_run",
        entity_id=run.id,
        dossier_id=run.dossier_id,
    )
    session.commit()

    key = get_master_key()
    enabled = providers.enabled_providers()
    collected: dict[str, list[providers.SearchResult]] = {}
    subject_kinds: dict[str, str] = {}
    errors: list[str] = []
    total_sources = 0

    for query in sorted(run.queries, key=lambda item: item.created_at):
        if not query.approved:
            continue
        try:
            redaction.assert_sendable(query.query_text, subject_kind=query.subject_kind)
        except redaction.PayloadRefused as exc:
            query.error_message = exc.message
            audit.record(
                session,
                audit.AuditAction.WEB_QUERY_REFUSED,
                f"Requête refusée avant envoi : {exc.message}",
                entity_type="web_query",
                entity_id=query.id,
                dossier_id=run.dossier_id,
            )
            continue

        query.sent_at = datetime.now(timezone.utc)
        results: list[providers.SearchResult] = []
        for provider in enabled:
            found, error = providers.safe_search(provider, query.query_text, limit=5)
            if error:
                errors.append(error)
                query.error_message = error
                audit.record(
                    session,
                    audit.AuditAction.WEB_PROVIDER_ERROR,
                    error,
                    entity_type="web_query",
                    entity_id=query.id,
                    dossier_id=run.dossier_id,
                )
                continue
            results.extend(found)
            query.provider = provider.name

        query.result_count = len(results)
        audit.record(
            session,
            audit.AuditAction.WEB_QUERY_SENT,
            f"Requête publique envoyée pour « {query.subject_label} » : {len(results)} résultat(s).",
            entity_type="web_query",
            entity_id=query.id,
            dossier_id=run.dossier_id,
            fingerprint=value_fingerprint(query.query_text),
        )

        for result in results:
            source = WebSource(
                run_id=run.id,
                query_id=query.id,
                url=result.url,
                domain=egress.domain_of(result.url),
                title=result.title,
                publisher=result.publisher,
                published_on=result.published_on,
                consulted_at=result.consulted_at or datetime.now(timezone.utc),
                tier=result.tier,
                content_sha256=sha256_bytes(result.snippet.encode("utf-8")),
                language=result.language,
            )
            session.add(source)
            session.flush()
            source.excerpt_cipher = encrypt_text(key, result.snippet[:600], source_aad(source.id))
            total_sources += 1

        collected.setdefault(query.subject_label, []).extend(results)
        subject_kinds[query.subject_label] = query.subject_kind

    session.commit()

    algerian_references = _algerian_references(session)
    claims_created = 0
    ranking_orchestration = None

    for subject_label, results in collected.items():
        data = AgentInput(
            subject_kind=subject_kinds.get(subject_label, "PERSONNE"),
            subject_label=subject_label,
            declared_affiliation=dossier.organizer if dossier else None,
            results=results,
            algerian_references=algerian_references,
        )
        orchestration = orchestrate(data)
        if subject_kinds.get(subject_label) == "MANIFESTATION" or ranking_orchestration is None:
            ranking_orchestration = orchestration

        profile = PersonWebProfile(
            dossier_id=run.dossier_id,
            run_id=run.id,
            subject_kind=data.subject_kind,
            display_name=subject_label,
            declared_affiliation=data.declared_affiliation,
            verified_affiliations_json=json.dumps(
                sorted({result.publisher for result in results if result.publisher}), ensure_ascii=False
            ),
            status=_profile_status(orchestration.claims),
        )
        session.add(profile)
        session.flush()

        for claim in orchestration.claims:
            record = OnlineClaim(
                run_id=run.id,
                dossier_id=run.dossier_id,
                agent_name=claim.agent_name,
                subject_label=claim.subject_label,
                statement_cipher=b"",
                nature=claim.nature,
                status=claim.status,
                confidence=claim.confidence,
                source_ids_json=json.dumps(claim.source_urls, ensure_ascii=False),
                independent_source_count=claim.independent_source_count,
            )
            session.add(record)
            session.flush()
            record.statement_cipher = encrypt_text(
                key, f"{claim.statement}\n{claim.notes}".strip(), claim_aad(record.id, "statement")
            )
            claims_created += 1

        for claim in orchestration.claims:
            if claim.status == EvidenceStatus.HOMONYMIE_POSSIBLE:
                session.add(
                    IdentityDisambiguation(
                        profile_id=profile.id,
                        candidate_label=subject_label,
                        candidate_affiliation=data.declared_affiliation,
                        discriminators_json=json.dumps(claim.source_urls, ensure_ascii=False),
                        decision=EvidenceStatus.HOMONYMIE_POSSIBLE,
                    )
                )

        for output in orchestration.outputs:
            for proposal in output.axis_proposals:
                assessment = AgentAssessment(
                    run_id=run.id,
                    agent_name=output.agent_name,
                    agent_version=output.agent_version,
                    subject_label=subject_label,
                    axis_key=proposal.axis_key,
                    proposed_score=proposal.proposed_score,
                    uncertainty_low=proposal.uncertainty_low,
                    uncertainty_high=proposal.uncertainty_high,
                    evidence_sufficient=proposal.evidence_sufficient,
                    source_ids_json=json.dumps(proposal.source_urls, ensure_ascii=False),
                )
                session.add(assessment)
                session.flush()
                assessment.rationale_cipher = encrypt_text(
                    key, proposal.rationale, f"assessment:{assessment.id}:rationale"
                )
            audit.record(
                session,
                audit.AuditAction.AGENT_RUN,
                f"{output.agent_name} v{output.agent_version} — {len(output.claims)} affirmation(s) "
                f"sur « {subject_label} ».",
                entity_type="web_research_run",
                entity_id=run.id,
                dossier_id=run.dossier_id,
            )

        for disagreement in orchestration.disagreements:
            audit.record(
                session,
                audit.AuditAction.AGENT_DISAGREEMENT,
                disagreement.description,
                entity_type="web_research_run",
                entity_id=run.id,
                dossier_id=run.dossier_id,
            )

    session.commit()

    if ranking_orchestration is not None:
        ranking_service.build_ranking(
            session,
            run.dossier_id,
            run_id=run.id,
            orchestration=ranking_orchestration,
            comparison_note=(
                "Comparaison limitée aux sources publiques consultées à la date indiquée."
            ),
        )

    run.status = WebRunStatus.TERMINEE if not errors else WebRunStatus.TERMINEE
    run.failure_reason = "; ".join(sorted(set(errors))) if errors else None
    run.finished_at = datetime.now(timezone.utc)
    session.commit()

    return {
        "run_id": run.id,
        "status": run.status,
        "online": True,
        "sources": total_sources,
        "claims": claims_created,
        "provider_errors": sorted(set(errors)),
        "message": (
            "Campagne terminée. Toutes les affirmations restent à vérifier par l'évaluateur ; "
            "aucune n'a valeur de décision."
        ),
    }


def _profile_status(claims) -> str:
    statuses = {claim.status for claim in claims}
    if EvidenceStatus.HOMONYMIE_POSSIBLE in statuses:
        return EvidenceStatus.HOMONYMIE_POSSIBLE
    if EvidenceStatus.SOURCES_CONTRADICTOIRES in statuses:
        return EvidenceStatus.SOURCES_CONTRADICTOIRES
    if EvidenceStatus.SOURCE_OFFICIELLE_TROUVEE in statuses:
        return EvidenceStatus.SOURCE_OFFICIELLE_TROUVEE
    if EvidenceStatus.SOURCES_CONCORDANTES in statuses:
        return EvidenceStatus.SOURCES_CONCORDANTES
    return EvidenceStatus.A_VERIFIER


def _algerian_references(session: Session) -> list[dict]:
    """Seuls les textes algériens validés, intègres et paginés sont utilisables."""
    regulations = session.scalars(select(Regulation)).all()
    references: list[dict] = []
    for regulation in regulations:
        references.append(
            {
                "id": regulation.id,
                "title": regulation.title,
                "reference": regulation.reference,
                "document_date": regulation.document_date,
                "status": regulation.status,
                "integrity_ok": bool(regulation.integrity_ok),
                "passages": [
                    {"id": passage.id, "page_no": passage.page_no}
                    for passage in regulation.passages
                ],
            }
        )
    return references


# --------------------------------------------------------------------------
# Pause, reprise, annulation, mise à l'écart
# --------------------------------------------------------------------------


def set_run_status(
    session: Session, run_id: str, *, status: str, justification: str = ""
) -> WebResearchRun:
    run = _get_run(session, run_id)
    settings = get_settings()
    mapping = {
        WebRunStatus.EN_PAUSE: audit.AuditAction.WEB_RUN_PAUSE,
        WebRunStatus.EN_COURS: audit.AuditAction.WEB_RUN_RESUME,
        WebRunStatus.ANNULEE: audit.AuditAction.WEB_RUN_CANCEL,
        WebRunStatus.ECARTEE_PAR_HUMAIN: audit.AuditAction.WEB_RUN_DISMISS,
    }
    if status not in mapping:
        raise ValidationRefused("Transition de campagne non autorisée.")
    if status == WebRunStatus.ECARTEE_PAR_HUMAIN:
        if len(justification.strip()) < settings.min_justification_length:
            raise ValidationRefused(
                "Écarter une recherche exige une justification humaine explicite "
                f"({settings.min_justification_length} caractères minimum)."
            )
        run.dismissal_justification = justification.strip()
    run.status = status
    audit.record(
        session,
        mapping[status],
        f"Campagne {run.id} → {status}." + (f" Motif : {justification.strip()}" if justification else ""),
        entity_type="web_research_run",
        entity_id=run.id,
        dossier_id=run.dossier_id,
    )
    session.commit()
    return run


def enriched_analysis_state(session: Session, dossier_id: str) -> dict:
    """Un dossier n'est `ANALYSE_ENRICHIE_COMPLETE` que si la recherche est aboutie."""
    runs = session.scalars(
        select(WebResearchRun)
        .where(WebResearchRun.dossier_id == dossier_id)
        .order_by(WebResearchRun.created_at.desc())
    ).all()
    if not runs:
        return {
            "complete": False,
            "reason": "Aucune campagne de recherche publique n'a été préparée.",
            "message": WEB_UNAVAILABLE_MESSAGE,
        }
    latest = runs[0]
    terminal = {
        WebRunStatus.TERMINEE,
        WebRunStatus.ECHOUEE,
        WebRunStatus.ECARTEE_PAR_HUMAIN,
    }
    complete = latest.status in terminal
    reasons = {
        WebRunStatus.TERMINEE: "Campagne terminée : résultats à vérifier par l'évaluateur.",
        WebRunStatus.ECHOUEE: f"Campagne explicitement en échec : {latest.failure_reason or WEB_UNAVAILABLE_MESSAGE}",
        WebRunStatus.ECARTEE_PAR_HUMAIN: "Recherche écartée avec justification humaine.",
    }
    return {
        "complete": complete,
        "run_id": latest.id,
        "status": latest.status,
        "reason": reasons.get(latest.status, "Campagne non terminée."),
        "message": (
            "Analyse enrichie considérée comme aboutie (terminée, en échec explicite ou écartée "
            "avec justification)."
            if complete
            else "Analyse enrichie incomplète : la campagne n'est ni terminée, ni explicitement "
            "en échec, ni écartée avec justification."
        ),
    }


def mark_enriched_complete(session: Session, dossier_id: str) -> Dossier:
    state = enriched_analysis_state(session, dossier_id)
    if not state["complete"]:
        raise ValidationRefused(state["message"])
    dossier = session.get(Dossier, dossier_id)
    if dossier is None:
        raise NotFound("Dossier introuvable.")
    dossier.status = DossierStatus.ANALYSE_ENRICHIE_COMPLETE
    audit.record(
        session,
        audit.AuditAction.DOSSIER_UPDATE,
        "État → ANALYSE_ENRICHIE_COMPLETE (recherche publique aboutie).",
        entity_type="dossier",
        entity_id=dossier.id,
        dossier_id=dossier.id,
    )
    session.commit()
    return dossier


# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------


def run_view(session: Session, run_id: str) -> dict:
    run = _get_run(session, run_id)
    key = get_master_key()
    sources = session.scalars(select(WebSource).where(WebSource.run_id == run.id)).all()
    claims = session.scalars(select(OnlineClaim).where(OnlineClaim.run_id == run.id)).all()
    return {
        "id": run.id,
        "dossier_id": run.dossier_id,
        "status": run.status,
        "scope_note": run.scope_note,
        "connectivity_ok": run.connectivity_ok,
        "providers": json.loads(run.providers_json),
        "approved_by": run.approved_by,
        "approved_at": run.approved_at,
        "failure_reason": run.failure_reason,
        "dismissal_justification": run.dismissal_justification,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "created_at": run.created_at,
        "queries": [
            {
                "id": query.id,
                "subject_kind": query.subject_kind,
                "subject_label": query.subject_label,
                "query_text": query.query_text,
                "purpose": query.purpose,
                "provider": query.provider,
                "approved": query.approved,
                "approved_by": query.approved_by,
                "sent_at": query.sent_at,
                "result_count": query.result_count,
                "error_message": query.error_message,
                "redaction_report": json.loads(query.redaction_report_json),
            }
            for query in sorted(run.queries, key=lambda item: item.created_at)
        ],
        "sources": [
            {
                "id": source.id,
                "url": source.url,
                "domain": source.domain,
                "title": source.title,
                "publisher": source.publisher,
                "published_on": source.published_on,
                "consulted_at": source.consulted_at,
                "tier": source.tier,
                "excerpt": decrypt_text(key, source.excerpt_cipher, source_aad(source.id)),
            }
            for source in sources
        ],
        "claims": [
            {
                "id": claim.id,
                "agent_name": claim.agent_name,
                "subject_label": claim.subject_label,
                "statement": decrypt_text(
                    key, claim.statement_cipher, claim_aad(claim.id, "statement")
                ),
                "nature": claim.nature,
                "status": claim.status,
                "human_status": claim.human_status,
                "confidence": claim.confidence,
                "sources": json.loads(claim.source_ids_json),
                "independent_source_count": claim.independent_source_count,
                "human_comment": decrypt_text(
                    key, claim.human_comment_cipher, claim_aad(claim.id, "comment")
                ),
            }
            for claim in claims
        ],
        "notice": (
            "Aucun document du dossier n'a été transmis. Chaque affirmation porte son URL, sa date "
            "de consultation, son type de source et son niveau de preuve. Rien ici ne vaut décision."
        ),
    }


def list_runs(session: Session, dossier_id: str) -> list[dict]:
    runs = session.scalars(
        select(WebResearchRun)
        .where(WebResearchRun.dossier_id == dossier_id)
        .order_by(WebResearchRun.created_at.desc())
    ).all()
    return [
        {
            "id": run.id,
            "status": run.status,
            "connectivity_ok": run.connectivity_ok,
            "approved_at": run.approved_at,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "failure_reason": run.failure_reason,
            "created_at": run.created_at,
        }
        for run in runs
    ]


def qualify_claim(session: Session, claim_id: str, *, status: str, comment: str) -> OnlineClaim:
    claim = session.get(OnlineClaim, claim_id)
    if claim is None:
        raise NotFound("Affirmation introuvable.")
    if status not in set(EvidenceStatus):
        raise ValidationRefused("Statut d'affirmation inconnu.")
    settings = get_settings()
    comment = (comment or "").strip()
    if status != EvidenceStatus.A_VERIFIER and len(comment) < settings.min_motivation_length:
        raise ValidationRefused(
            f"Une motivation d'au moins {settings.min_motivation_length} caractères est obligatoire."
        )
    claim.human_status = status
    claim.human_comment_cipher = encrypt_text(
        get_master_key(), comment, claim_aad(claim.id, "comment")
    )
    audit.record(
        session,
        audit.AuditAction.WEB_CLAIM_QUALIFY,
        f"Affirmation de {claim.agent_name} sur « {claim.subject_label} » → {status}.",
        entity_type="online_claim",
        entity_id=claim.id,
        dossier_id=claim.dossier_id,
        fingerprint=value_fingerprint(comment),
    )
    session.commit()
    return claim


def _get_run(session: Session, run_id: str) -> WebResearchRun:
    run = session.get(WebResearchRun, run_id)
    if run is None:
        raise NotFound("Campagne de recherche introuvable.")
    return run


__all__ = [
    "ClaimNature",
    "approve_run",
    "connectivity",
    "edit_query",
    "enriched_analysis_state",
    "execute_run",
    "list_runs",
    "mark_enriched_complete",
    "prepare_run",
    "qualify_claim",
    "run_view",
    "set_run_status",
]
