"""Construction des faits du dossier, source unique des moteurs déterministes.

Les moteurs réglementaire et scientifique ne lisent jamais la base directement :
ils reçoivent un `DossierFacts` déjà constitué, ce qui les rend testables sans
base et garantit que les deux raisonnent sur exactement les mêmes faits.

Un principe gouverne tout ce module : **ce qui n'est pas documenté n'est pas
compté**. Un effectif dont aucune affiliation n'est lisible n'est pas ramené à
zéro — il est laissé indéterminé, et le critère devient « non vérifiable ».
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_text
from app.core.keyring import get_master_key
from app.core.text import contains_term, normalize
from app.core.vocabulary import InformationStatus
from app.models import ExtractedItem, Finding
from app.services import dossier_service, evidence_service, extraction_service
from app.services.regulatory_engine import CONTINENTS, DossierFacts

URL_PATTERN = re.compile(r"https?://[^\s,;)\]]+")

#: Séparateurs d'une liste nominative (comité, intervenants).
ROSTER_SPLIT = re.compile(r"[;\n]|(?<=[a-zà-ÿ])\s*,\s*(?=[A-ZÀ-Ý])|\s+/\s+")

#: Titres et civilités retirés avant de décider qu'une entrée nomme quelqu'un.
ROSTER_NOISE = ("pr", "prof", "professeur", "dr", "docteur", "mr", "mme", "m", "monsieur", "madame")

ALGERIA = "algérie"


def _roster_entries(value: str | None) -> list[str]:
    """Découpe une liste nominative en entrées exploitables."""
    if not value:
        return []
    entries = []
    for chunk in ROSTER_SPLIT.split(value):
        if chunk is None:
            continue
        candidate = chunk.strip(" .,-–—\t")
        if not candidate:
            continue
        letters = [
            token
            for token in normalize(candidate).split()
            if token not in ROSTER_NOISE and len(token) > 1
        ]
        if letters:
            entries.append(candidate)
    return entries


def _entry_country(entry: str) -> str | None:
    """Pays explicitement nommé dans une entrée, ou None si non documenté."""
    normalized = normalize(entry)
    for country in CONTINENTS:
        if contains_term(normalized, country) is not None:
            return country
    return None


def _roster_counts(value: str | None) -> tuple[int | None, int | None, list[str]]:
    """Retourne (total, étrangers, pays repérés).

    `total` et `étrangers` valent `None` tant qu'aucune entrée ne porte de pays :
    dans ce cas la proportion n'est **pas calculable**, et le dire est la seule
    réponse exacte.
    """
    entries = _roster_entries(value)
    if not entries:
        return None, None, []
    countries = [country for entry in entries if (country := _entry_country(entry))]
    if not countries:
        return None, None, []
    foreign = [country for country in countries if country != ALGERIA]
    return len(entries), len(foreign), sorted(set(countries))


def _values(session: Session, dossier_id: str) -> dict[str, str]:
    """Valeurs courantes des informations, hors valeurs explicitement rejetées."""
    key = get_master_key()
    values: dict[str, str] = {}
    items = session.scalars(
        select(ExtractedItem).where(ExtractedItem.dossier_id == dossier_id)
    ).all()
    for item in items:
        if item.status in {InformationStatus.REJETE, InformationStatus.NON_APPLICABLE}:
            continue
        value = decrypt_text(
            key, item.current_value_cipher, dossier_service.item_aad(item.id, "current")
        )
        if value and value.strip():
            values[item.key] = value.strip()
    return values


def _findings(session: Session, dossier_id: str) -> list[dict]:
    rows = session.scalars(select(Finding).where(Finding.dossier_id == dossier_id)).all()
    return [
        {
            "id": row.id,
            "rule_code": row.rule_code,
            "category": row.category,
            "priority": row.priority,
            "status": row.human_status,
            "human_status": row.human_status,
            "page_no": row.page_no,
            "label": row.label,
        }
        for row in rows
    ]


def build_facts(session: Session, dossier_id: str, *, rebuild_evidence: bool = True) -> DossierFacts:
    """Rassemble tout ce que l'application sait du dossier, avec ses preuves."""
    pages = dossier_service.dossier_page_texts(session, dossier_id)
    values = _values(session, dossier_id)
    report = extraction_service.analyze_text(pages)
    observations = dict(report.observations)

    # Effectifs du comité et des intervenants — indéterminés si non documentés.
    committee_total, committee_foreign, committee_countries = _roster_counts(
        values.get("comite_scientifique")
    )
    speakers_total, speakers_foreign, speaker_countries = _roster_counts(
        values.get("intervenants")
    )
    observations["membres_total"] = committee_total
    observations["membres_etrangers"] = committee_foreign
    observations["intervenants_total"] = speakers_total
    observations["intervenants_etrangers_presents"] = speakers_foreign
    observations["pays_comite"] = committee_countries
    observations["pays_intervenants"] = speaker_countries

    full_text = "\n".join(pages[page] for page in sorted(pages))
    observations["urls"] = sorted(set(URL_PATTERN.findall(full_text)))

    pieces = {
        piece.piece_key: piece.status
        for piece in dossier_service.dossier_pieces(session, dossier_id)
    }

    evidence = (
        evidence_service.rebuild_registry(session, dossier_id)
        if rebuild_evidence
        else {
            f"page:{page_no}": f"E-P{page_no:03d}" for page_no in pages
        }
    )

    return DossierFacts(
        values=values,
        pages=pages,
        observations=observations,
        pieces=pieces,
        findings=_findings(session, dossier_id),
        evidence=evidence,
    )
