"""Registre de preuves — toute affirmation du rapport doit y être rattachée.

Une preuve porte : une référence lisible et stable (« E-P3-004 »), une origine,
une page ou un localisateur, l'extrait chiffré et l'empreinte SHA-256 du
contenu cité. Le validateur refuse tout `evidence_id` inconnu : un rapport ne
peut pas citer une preuve qui n'existe pas.

Les pièces d'identité sont enregistrées comme preuves **restreintes** : leur
existence est traçable, leur contenu n'est jamais transmis au modèle, à une
recherche Web, ni reproduit dans le rapport.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_text, encrypt_text
from app.core.keyring import get_master_key
from app.core.vocabulary import EvidenceKind, Sensitivity
from app.models import EvidenceItem
from app.services import dossier_service

EXCERPT_LIMIT = 600


class UnknownEvidence(ValueError):
    """Levée lorsqu'une affirmation cite une preuve absente du registre."""


def evidence_aad(evidence_id: str) -> str:
    return f"evidence:{evidence_id}:excerpt"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass
class EvidenceDraft:
    reference: str
    kind: str
    excerpt: str
    page_no: int | None = None
    locator: str | None = None
    sensitivity: str = Sensitivity.ORDINAIRE


def _page_reference(page_no: int) -> str:
    return f"E-P{page_no:03d}"


def _piece_reference(index: int) -> str:
    return f"E-PJ{index:03d}"


def _calculation_reference(key: str) -> str:
    digest = _sha256(key)[:6].upper()
    return f"E-C{digest}"


def rebuild_registry(session: Session, dossier_id: str) -> dict[str, str]:
    """Reconstruit le registre à partir de l'état courant du dossier.

    Retourne la table `clé logique -> référence de preuve`, utilisée par les
    moteurs pour citer leurs sources sans connaître le stockage.
    """
    key = get_master_key()
    existing = {
        item.reference: item
        for item in session.scalars(
            select(EvidenceItem).where(EvidenceItem.dossier_id == dossier_id)
        ).all()
    }

    drafts: list[tuple[str, EvidenceDraft]] = []

    for page in dossier_service.dossier_pages(session, dossier_id):
        text = dossier_service.page_text(page) or ""
        if not text.strip():
            continue
        drafts.append(
            (
                f"page:{page.page_no}",
                EvidenceDraft(
                    reference=_page_reference(page.page_no),
                    kind=EvidenceKind.PAGE,
                    excerpt=text[:EXCERPT_LIMIT],
                    page_no=page.page_no,
                    locator=f"page {page.page_no}",
                ),
            )
        )

    for index, piece in enumerate(dossier_service.dossier_pieces(session, dossier_id), start=1):
        drafts.append(
            (
                f"piece:{piece.piece_key}",
                EvidenceDraft(
                    reference=_piece_reference(index),
                    kind=EvidenceKind.PIECE,
                    # Le contenu d'une pièce restreinte n'est jamais recopié ici.
                    excerpt=(
                        f"{piece.label} — statut {piece.status}"
                        if piece.sensitivity != Sensitivity.RESTREINT
                        else f"{piece.label} — pièce restreinte, contenu non reproduit "
                        f"(statut {piece.status})"
                    ),
                    page_no=piece.detected_page_no,
                    locator=f"pièce {piece.piece_key}",
                    sensitivity=piece.sensitivity,
                ),
            )
        )

    mapping: dict[str, str] = {}
    for logical_key, draft in drafts:
        content_hash = _sha256(draft.excerpt)
        item = existing.get(draft.reference)
        if item is None:
            item = EvidenceItem(
                dossier_id=dossier_id,
                reference=draft.reference,
                kind=draft.kind,
                page_no=draft.page_no,
                locator=draft.locator,
                content_sha256=content_hash,
                sensitivity=draft.sensitivity,
            )
            session.add(item)
            session.flush()
        else:
            item.kind = draft.kind
            item.page_no = draft.page_no
            item.locator = draft.locator
            item.content_sha256 = content_hash
            item.sensitivity = draft.sensitivity
        item.excerpt_cipher = encrypt_text(key, draft.excerpt, evidence_aad(item.id))
        mapping[logical_key] = draft.reference

    session.flush()
    return mapping


def register_calculation(
    session: Session, dossier_id: str, *, key_name: str, payload: dict
) -> str:
    """Enregistre un calcul comme preuve citable et retourne sa référence."""
    master = get_master_key()
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    reference = _calculation_reference(f"{dossier_id}:{key_name}")
    item = session.scalar(
        select(EvidenceItem).where(
            EvidenceItem.dossier_id == dossier_id, EvidenceItem.reference == reference
        )
    )
    if item is None:
        item = EvidenceItem(
            dossier_id=dossier_id,
            reference=reference,
            kind=EvidenceKind.CALCUL,
            locator=key_name,
        )
        session.add(item)
        session.flush()
    item.content_sha256 = _sha256(serialized)
    item.excerpt_cipher = encrypt_text(master, serialized[:EXCERPT_LIMIT], evidence_aad(item.id))
    session.flush()
    return reference


def known_references(session: Session, dossier_id: str) -> set[str]:
    return set(
        session.scalars(
            select(EvidenceItem.reference).where(EvidenceItem.dossier_id == dossier_id)
        ).all()
    )


def validate_references(session: Session, dossier_id: str, references: list[str]) -> None:
    """Refuse toute citation d'une preuve absente du registre."""
    known = known_references(session, dossier_id)
    unknown = sorted({ref for ref in references if ref not in known})
    if unknown:
        raise UnknownEvidence(
            "Preuves citées mais absentes du registre : " + ", ".join(unknown) + ". "
            "Une affirmation ne peut pas s'appuyer sur une preuve inexistante."
        )


def read_excerpt(session: Session, evidence_id: str) -> str | None:
    item = session.get(EvidenceItem, evidence_id)
    if item is None:
        return None
    return decrypt_text(get_master_key(), item.excerpt_cipher, evidence_aad(item.id))


def listing(session: Session, dossier_id: str) -> list[dict]:
    """Liste consultable dans l'application : « Voir les preuves »."""
    items = session.scalars(
        select(EvidenceItem)
        .where(EvidenceItem.dossier_id == dossier_id)
        .order_by(EvidenceItem.kind, EvidenceItem.reference)
    ).all()
    key = get_master_key()
    rows: list[dict] = []
    for item in items:
        excerpt = decrypt_text(key, item.excerpt_cipher, evidence_aad(item.id))
        restricted = item.sensitivity == Sensitivity.RESTREINT
        rows.append(
            {
                "id": item.id,
                "reference": item.reference,
                "kind": item.kind,
                "page_no": item.page_no,
                "locator": item.locator,
                "sensitivity": item.sensitivity,
                "content_sha256": item.content_sha256,
                "excerpt": (
                    "Pièce restreinte — contenu non affiché et jamais transmis à l'extérieur."
                    if restricted
                    else (excerpt or "")[:400]
                ),
            }
        )
    return rows
