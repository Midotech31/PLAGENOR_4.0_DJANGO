"""Normalisation de texte multilingue (français, anglais, arabe).

La comparaison est déterministe et explicable : chaque rapprochement conserve
les deux graphies d'origine et la métrique utilisée.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

#: Diacritiques arabes (harakat) et tatweel, retirés avant comparaison.
_ARABIC_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\s؀-ۿ]", re.UNICODE)

#: Caractères arabes normalisés vers une forme canonique.
_ARABIC_FOLD = {
    "أ": "ا",  # أ -> ا
    "إ": "ا",  # إ -> ا
    "آ": "ا",  # آ -> ا
    "ٱ": "ا",
    "ة": "ه",  # ة -> ه
    "ى": "ي",  # ى -> ي
    "ی": "ي",
}


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def normalize(value: str) -> str:
    """Forme normalisée : minuscules, sans accent, sans diacritique arabe."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = _ARABIC_DIACRITICS.sub("", text)
    text = "".join(_ARABIC_FOLD.get(ch, ch) for ch in text)
    text = strip_accents(text).lower()
    text = _PUNCTUATION.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def normalize_key(value: str) -> str:
    """Clé de rapprochement (mots triés) pour noms et institutions."""
    return " ".join(sorted(normalize(value).split()))


def contains_term(haystack_normalized: str, term: str) -> int | None:
    """Recherche un terme normalisé avec frontières de mot.

    Retourne l'index de début dans `haystack_normalized`, ou None.
    Les frontières empêchent qu'un terme court corresponde à l'intérieur d'un
    mot (« mali » dans « malicieux », « ma » dans « majeur »).
    """
    needle = normalize(term)
    if not needle or not haystack_normalized:
        return None
    start = 0
    while True:
        index = haystack_normalized.find(needle, start)
        if index == -1:
            return None
        before_ok = index == 0 or not _is_word_char(haystack_normalized[index - 1])
        end = index + len(needle)
        after_ok = end >= len(haystack_normalized) or not _is_word_char(haystack_normalized[end])
        if before_ok and after_ok:
            return index
        start = index + 1


def _is_word_char(char: str) -> bool:
    return char.isalnum() or char == "_"


def excerpt_around(text: str, normalized_index: int, normalized_text: str, width: int = 160) -> str:
    """Extrait un contexte lisible autour d'une correspondance.

    Le mapping normalisé -> original n'étant pas bijectif, on retombe sur une
    fenêtre proportionnelle, ce qui reste suffisant pour un contrôle humain
    (le lien « Voir la source » ouvre la page réelle).
    """
    if not text:
        return ""
    if not normalized_text:
        return text[:width]
    ratio = len(text) / max(len(normalized_text), 1)
    center = int(normalized_index * ratio)
    start = max(0, center - width // 2)
    end = min(len(text), start + width)
    prefix = "… " if start > 0 else ""
    suffix = " …" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def similarity(left: str, right: str) -> float:
    """Similarité 0..1 entre deux graphies normalisées (SequenceMatcher)."""
    a, b = normalize(left), normalize(right)
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a, b).ratio(), 4)


def containment(needle: str, haystack: str) -> float:
    """Mesure « le court est-il contenu dans le long ? », entre 0 et 1.

    La similarité globale est inadaptée pour comparer une affiliation courte à
    un titre long : elle chute mécaniquement avec la différence de longueur.
    Cette métrique compare la proportion de mots du terme court retrouvés dans
    le texte long, ce qui reste explicable et affichable à l'évaluateur.
    """
    short = normalize(needle)
    long = normalize(haystack)
    if not short or not long:
        return 0.0
    if short in long:
        return 1.0
    short_tokens = [token for token in short.split() if len(token) > 2]
    if not short_tokens:
        return 0.0
    long_tokens = set(long.split())
    matched = sum(1 for token in short_tokens if token in long_tokens)
    return round(matched / len(short_tokens), 4)


def best_match(needle: str, candidates: list[str]) -> tuple[float, str | None]:
    """Meilleure correspondance et sa métrique, pour un rapprochement explicable."""
    best_score = 0.0
    best_value: str | None = None
    for candidate in candidates:
        score = containment(needle, candidate)
        if score > best_score:
            best_score, best_value = score, candidate
    return best_score, best_value


def useful_char_count(text: str) -> int:
    """Nombre de caractères réellement utiles (hors espaces et ponctuation)."""
    return sum(1 for ch in normalize(text) if not ch.isspace())
