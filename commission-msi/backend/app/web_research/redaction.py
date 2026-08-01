"""Garde-fou des données sortantes.

Seule une requête minimale et publique peut quitter le poste : nom public,
affiliation, institution, intitulé de manifestation ou identifiant public.
Tout le reste — PDF, pièce, document d'identité, note interne, donnée
personnelle non nécessaire — est refusé avant l'appel réseau.
"""

from __future__ import annotations

import re

from app.core.errors import AppError

MAX_QUERY_LENGTH = 300


class PayloadRefused(AppError):
    """Contenu refusé avant tout envoi vers un fournisseur externe."""

    code = "ENVOI_REFUSE"
    status_code = 422


#: Motifs interdits dans une requête sortante.
FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"%PDF-", "contenu de fichier PDF"),
    (r"\bpasseport\b|\bpassport\b|جواز\s*السفر", "référence à un document d'identité"),
    (r"\bcarte\s+nationale\b|\bcin\b|\bnational\s+id\b", "référence à une pièce d'identité"),
    (r"\b\d{9,}\b", "identifiant numérique long (numéro de document ou de téléphone)"),
    (r"[\w.+-]+@[\w-]+\.[\w.]+", "adresse de courriel"),
    (r"\+\d[\d\s().-]{7,}", "numéro de téléphone"),
    (r"\biban\b|\brib\b|\bnuméro\s+de\s+compte\b", "coordonnée bancaire"),
    (r"\bdate\s+de\s+naissance\b|\bdate\s+of\s+birth\b|\bné\s+le\b", "donnée d'état civil"),
    (r"\badresse\s+(personnelle|privée|du\s+domicile)\b|\bhome\s+address\b", "adresse privée"),
    (r"\bdossier\s+n[°o]\s*\S+", "référence interne de dossier"),
    (r"\bnote\s+interne\b|\bconfidentiel\b|\bconfidential\b", "mention de document interne"),
    (r"\bdonnées?\s+de\s+santé\b|\bmedical\s+record\b", "donnée de santé"),
)

#: Champs publics autorisés comme sujet d'une requête.
ALLOWED_SUBJECT_KINDS = frozenset(
    {
        "PERSONNE",
        "INSTITUTION",
        "PARTENAIRE",
        "SPONSOR",
        "FINANCEUR",
        "MANIFESTATION",
        "IDENTIFIANT_PUBLIC",
    }
)


def inspect(text: str) -> list[str]:
    """Retourne la liste des motifs interdits trouvés dans `text`."""
    findings: list[str] = []
    for pattern, label in FORBIDDEN_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            findings.append(label)
    return findings


def assert_sendable(query_text: str, *, subject_kind: str) -> dict:
    """Valide une requête avant envoi. Lève :class:`PayloadRefused` si elle est refusée."""
    text = (query_text or "").strip()
    if not text:
        raise PayloadRefused("Requête vide : rien n'est envoyé.")
    if subject_kind not in ALLOWED_SUBJECT_KINDS:
        raise PayloadRefused(
            f"Type de sujet « {subject_kind} » non autorisé pour une requête sortante."
        )
    if len(text) > MAX_QUERY_LENGTH:
        raise PayloadRefused(
            f"Requête trop longue ({len(text)} caractères, maximum {MAX_QUERY_LENGTH}). "
            "Une requête sortante doit rester minimale."
        )
    if "\n" in text or "\r" in text:
        raise PayloadRefused("Une requête sortante doit tenir sur une seule ligne.")

    findings = inspect(text)
    if findings:
        raise PayloadRefused(
            "Envoi refusé : la requête contient " + ", ".join(sorted(set(findings))) + ". "
            "Seuls un nom public, une affiliation, une institution, un intitulé de manifestation "
            "ou un identifiant public peuvent être transmis."
        )
    return {
        "length": len(text),
        "subject_kind": subject_kind,
        "forbidden_patterns_found": [],
        "verdict": "AUTORISEE",
    }


def assert_no_document(payload: bytes | str) -> None:
    """Refuse explicitement l'envoi d'un document, quelle qu'en soit la raison."""
    sample = payload[:4096]
    if isinstance(sample, bytes):
        try:
            sample = sample.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - contenu binaire = refus direct
            raise PayloadRefused("Envoi d'un contenu binaire refusé.") from None
    if sample.lstrip().startswith("%PDF-"):
        raise PayloadRefused(
            "Envoi d'un PDF refusé : le document original ne quitte jamais le poste."
        )
    findings = inspect(sample)
    if findings:
        raise PayloadRefused(
            "Envoi refusé : le contenu comporte " + ", ".join(sorted(set(findings))) + "."
        )
