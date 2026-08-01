"""Moteur de vigilance déterministe.

Le moteur ne décide jamais. Il produit des alertes explicables : terme
déclencheur, contexte, page, confiance, explication, vérification recommandée
et statut humain initial `A_VERIFIER`. Aucune alerte ne peut se transformer en
note, en conformité, en interdiction ou en conclusion.

Aucune IA générative n'intervient : la détection repose sur des termes
versionnés, une normalisation multilingue et des frontières de mots.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.text import contains_term, excerpt_around, normalize
from app.core.vocabulary import Priority
from app.models import Rule

#: Titre exact imposé pour la section Maroc.
MAROC_TITLE = "Mentions relatives au Maroc — vérification institutionnelle obligatoire"
MAROC_NOTICE = (
    "Point de vigilance institutionnelle — vérifier les instructions officielles "
    "applicables à la session avant toute conclusion."
)

#: Confiance attribuée à une détection. Elle qualifie la détection textuelle,
#: jamais la réalité du risque.
CONFIDENCE_PRIMARY = 0.9
CONFIDENCE_SECONDARY_WITH_CONTEXT = 0.55

#: Distance maximale (en caractères normalisés) entre un indice secondaire et un
#: terme de contexte institutionnel pour que l'indice soit retenu.
CONTEXT_WINDOW = 220

DISCLAIMER = (
    "Alerte de vérification humaine. Elle ne constitue ni une décision, ni une "
    "interdiction, ni une note. L'absence d'alerte ne prouve pas l'absence de risque."
)


@dataclass(frozen=True)
class RuleSpec:
    """Règle chargée en mémoire, prête pour l'analyse."""

    code: str
    category: str
    label: str
    priority: str
    terms: tuple[str, ...]
    secondary_terms: tuple[str, ...]
    context_terms: tuple[str, ...]
    guidance: str
    source_ref: str
    version: str
    is_normative: bool

    @property
    def is_validated_source(self) -> bool:
        return "à confirmer" not in self.source_ref.lower()


@dataclass
class Detection:
    rule_code: str
    rule_version: str
    category: str
    label: str
    priority: str
    trigger: str
    context: str
    page_no: int
    confidence: float
    explanation: str
    recommended_check: str
    source_ref: str
    match_kind: str  # PRIMAIRE | INDICE_SECONDAIRE
    signature: str = field(default="")

    def compute_signature(self) -> str:
        raw = f"{self.rule_code}|{self.page_no}|{normalize(self.trigger)}|{self.match_kind}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_active_rules(session: Session) -> list[RuleSpec]:
    """Charge les règles applicables.

    Une règle normative est exclue : elle ne peut produire d'état de conformité
    tant que sa source officielle n'est pas présente, validée et non contredite.
    """
    rules = session.scalars(select(Rule).where(Rule.active.is_(True))).all()
    specs: list[RuleSpec] = []
    for rule in rules:
        if rule.is_normative:
            continue
        specs.append(
            RuleSpec(
                code=rule.code,
                category=rule.category,
                label=rule.label,
                priority=rule.priority,
                terms=tuple(json.loads(rule.terms_json)),
                secondary_terms=tuple(json.loads(rule.secondary_terms_json)),
                context_terms=tuple(json.loads(rule.context_terms_json)),
                guidance=rule.guidance,
                source_ref=rule.source_ref,
                version=rule.version,
                is_normative=rule.is_normative,
            )
        )
    return specs


def scan_page(spec: RuleSpec, page_no: int, text: str) -> list[Detection]:
    """Applique une règle à une page et renvoie ses détections."""
    if not text:
        return []
    normalized = normalize(text)
    if not normalized:
        return []

    detections: list[Detection] = []
    matched_primary: set[str] = set()

    for term in spec.terms:
        index = contains_term(normalized, term)
        if index is None:
            continue
        key = normalize(term)
        if key in matched_primary:
            continue
        matched_primary.add(key)
        detections.append(
            _build(
                spec,
                page_no,
                term,
                excerpt_around(text, index, normalized),
                CONFIDENCE_PRIMARY,
                "PRIMAIRE",
            )
        )

    # Les indices secondaires (ville, domaine, indicatif) ne sont retenus que
    # s'ils apparaissent près d'un terme institutionnel ou d'affiliation.
    if spec.secondary_terms and spec.context_terms:
        context_positions = [
            index
            for term in spec.context_terms
            if (index := contains_term(normalized, term)) is not None
        ]
        if context_positions:
            for term in spec.secondary_terms:
                index = contains_term(normalized, term)
                if index is None:
                    continue
                if not any(abs(index - position) <= CONTEXT_WINDOW for position in context_positions):
                    continue
                detections.append(
                    _build(
                        spec,
                        page_no,
                        term,
                        excerpt_around(text, index, normalized),
                        CONFIDENCE_SECONDARY_WITH_CONTEXT,
                        "INDICE_SECONDAIRE",
                    )
                )

    return detections


def _build(
    spec: RuleSpec,
    page_no: int,
    trigger: str,
    context: str,
    confidence: float,
    match_kind: str,
) -> Detection:
    if match_kind == "INDICE_SECONDAIRE":
        explanation = (
            f"Indice secondaire « {trigger} » trouvé à proximité d'un terme institutionnel. "
            "Un indice de ce type (ville, domaine, indicatif) ne prouve jamais à lui seul "
            "une affiliation, une participation ou une coopération. " + DISCLAIMER
        )
    else:
        explanation = (
            f"Terme « {trigger} » détecté dans le texte de la page {page_no}. "
            "La détection porte sur le mot, pas sur sa signification. " + DISCLAIMER
        )

    recommended = spec.guidance
    if spec.category == "MENTIONS_MAROC":
        recommended = f"{MAROC_NOTICE} {spec.guidance}"

    return Detection(
        rule_code=spec.code,
        rule_version=spec.version,
        category=spec.category,
        label=MAROC_TITLE if spec.category == "MENTIONS_MAROC" else spec.label,
        priority=spec.priority if spec.priority in set(Priority) else Priority.MOYEN,
        trigger=trigger,
        context=context,
        page_no=page_no,
        confidence=confidence,
        explanation=explanation,
        recommended_check=recommended,
        source_ref=spec.source_ref,
        match_kind=match_kind,
    )


def scan_pages(specs: list[RuleSpec], pages: dict[int, str]) -> list[Detection]:
    """Applique toutes les règles actives à toutes les pages fournies."""
    detections: list[Detection] = []
    for page_no in sorted(pages):
        text = pages[page_no]
        for spec in specs:
            detections.extend(scan_page(spec, page_no, text))
    for detection in detections:
        detection.signature = detection.compute_signature()
    return detections


def unreadable_page_notice(page_no: int) -> Detection:
    """Alerte explicite pour une page illisible pouvant contenir un terme sensible.

    Une page non extraite n'est jamais présentée comme « sans risque ».
    """
    detection = Detection(
        rule_code="VIGILANCE-PAGE-ILLISIBLE",
        rule_version="1.0",
        category="COUVERTURE_ANALYSE",
        label="Page non extraite — couverture de vigilance incomplète",
        priority=Priority.ELEVE,
        trigger=f"page {page_no}",
        context="",
        page_no=page_no,
        confidence=1.0,
        explanation=(
            f"Le texte de la page {page_no} n'a pas pu être extrait de façon fiable. "
            "Aucune règle de vigilance n'a donc pu s'y appliquer : cette page peut contenir "
            "un terme sensible non détecté. " + DISCLAIMER
        ),
        recommended_check=(
            "Lancer l'OCR local sur cette page, ou lire la page originale à l'écran, "
            "puis qualifier manuellement le résultat."
        ),
        source_ref="Contrat de fiabilité — porte G1_EXTRACTION",
        match_kind="COUVERTURE",
    )
    detection.signature = detection.compute_signature()
    return detection
