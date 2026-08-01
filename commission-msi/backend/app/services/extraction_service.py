"""Extraction automatique des informations structurées du dossier.

L'application **propose** ; l'évaluateur **confirme**. Chaque valeur extraite
est enregistrée avec sa page, son extrait source, son mode d'extraction et une
confiance, au statut `A_VERIFIER`. Aucune valeur n'est confirmée
automatiquement, aucune n'est inventée : un champ qui n'a pas de correspondance
textuelle reste vide.

La détection est déterministe et explicable : expressions régulières
versionnées, listes de termes multilingues (français, anglais, arabe) et
normalisation. Aucun modèle génératif n'intervient.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.core.crypto import encrypt_text, value_fingerprint
from app.core.keyring import get_master_key
from app.core.text import contains_term, normalize
from app.core.vocabulary import ExtractionMode, InformationStatus
from app.models import ExtractedItem
from app.services import dossier_service

#: Confiance attribuée selon la précision du motif ayant produit la valeur.
CONFIDENCE_LABELLED = 0.85  # valeur précédée d'un libellé explicite
CONFIDENCE_PATTERN = 0.7  # motif structurel (date, montant, institution)
CONFIDENCE_HEURISTIC = 0.5  # heuristique de position ou de fréquence

MAX_VALUE_LENGTH = 1200
EXCERPT_WIDTH = 240


# --------------------------------------------------------------------------
# Vocabulaires de détection
# --------------------------------------------------------------------------

MONTHS = {
    "janvier": 1, "january": 1, "jan": 1, "يناير": 1, "جانفي": 1,
    "fevrier": 2, "february": 2, "feb": 2, "fev": 2, "فيفري": 2, "فبراير": 2,
    "mars": 3, "march": 3, "mar": 3, "مارس": 3,
    "avril": 4, "april": 4, "apr": 4, "avr": 4, "أفريل": 4, "أبريل": 4,
    "mai": 5, "may": 5, "ماي": 5, "مايو": 5,
    "juin": 6, "june": 6, "jun": 6, "جوان": 6, "يونيو": 6,
    "juillet": 7, "july": 7, "jul": 7, "juil": 7, "جويلية": 7, "يوليو": 7,
    "aout": 8, "august": 8, "aug": 8, "أوت": 8, "أغسطس": 8,
    "septembre": 9, "september": 9, "sep": 9, "sept": 9, "سبتمبر": 9,
    "octobre": 10, "october": 10, "oct": 10, "أكتوبر": 10,
    "novembre": 11, "november": 11, "nov": 11, "نوفمبر": 11,
    "decembre": 12, "december": 12, "dec": 12, "ديسمبر": 12,
}

EVENT_KINDS = (
    "colloque international", "conference internationale", "congres international",
    "seminaire international", "symposium international", "journee internationale",
    "colloque", "conference", "congres", "seminaire", "symposium", "workshop",
    "journee d etude", "journees d etudes", "table ronde", "atelier",
    "international conference", "international congress", "international symposium",
    "ملتقى دولي", "مؤتمر دولي", "ندوة دولية", "ملتقى", "مؤتمر", "ندوة",
)

FORMAT_TERMS = {
    "presentiel": "présentiel",
    "en presentiel": "présentiel",
    "hybride": "hybride",
    "hybrid": "hybride",
    "distanciel": "à distance",
    "a distance": "à distance",
    "en ligne": "à distance",
    "visioconference": "à distance",
    "videoconference": "à distance",
    "online": "à distance",
    "حضوري": "présentiel",
    "عن بعد": "à distance",
}

INSTITUTION_PREFIXES = (
    "universite", "university", "universita", "universidad", "universiti",
    "ecole superieure", "ecole nationale", "ecole polytechnique", "ecole",
    "institut", "institute", "instituto", "faculte", "faculty",
    "centre de recherche", "research center", "research centre", "laboratoire",
    "laboratory", "college", "academy", "academie", "school of",
    "جامعة", "المدرسة", "معهد", "كلية", "مخبر", "مركز",
)

#: Devises reconnues, avec leur forme normalisée.
CURRENCIES = {
    "da": "DA", "dzd": "DA", "dinars": "DA", "dinar": "DA", "دج": "DA", "دينار": "DA",
    "eur": "EUR", "euro": "EUR", "euros": "EUR", "€": "EUR",
    "usd": "USD", "dollar": "USD", "dollars": "USD", "$": "USD",
}

#: Pays fréquemment cités. La liste sert au dénombrement, jamais à conclure.
COUNTRIES = (
    "Algérie", "Algeria", "France", "Maroc", "Morocco", "Tunisie", "Tunisia",
    "Espagne", "Spain", "Italie", "Italy", "Allemagne", "Germany", "Belgique",
    "Belgium", "Canada", "Suisse", "Switzerland", "Portugal", "Royaume-Uni",
    "United Kingdom", "États-Unis", "United States", "Turquie", "Turkey",
    "Égypte", "Egypt", "Arabie saoudite", "Saudi Arabia", "Jordanie", "Jordan",
    "Liban", "Lebanon", "Qatar", "Émirats arabes unis", "Malaisie", "Malaysia",
    "Chine", "China", "Japon", "Japan", "Inde", "India", "Brésil", "Brazil",
    "Sénégal", "Senegal", "Mali", "Niger", "Libye", "Libya", "Mauritanie",
    "Nigeria", "Afrique du Sud", "South Africa", "Pays-Bas", "Netherlands",
    "Pologne", "Poland", "Roumanie", "Romania", "Grèce", "Greece", "Russie",
)

#: Libellés précédant une valeur. (clé du champ, variantes du libellé)
LABELLED_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("intitule", ("intitule", "titre", "theme de la manifestation", "title", "عنوان")),
    ("theme", ("theme", "thematique", "thematiques", "axes thematiques", "topic", "محور")),
    ("objectifs", ("objectifs", "objectif", "objectives", "but", "finalite", "أهداف")),
    ("lieu", ("lieu", "lieu de la manifestation", "venue", "location", "المكان")),
    ("format", ("format", "mode d organisation", "modalite", "mode", "نمط")),
    ("etablissement_organisateur", ("etablissement organisateur", "organisateur", "organise par", "organized by", "الجهة المنظمة")),
    ("structure_porteuse", ("structure porteuse", "structure d appui", "laboratoire organisateur", "faculte organisatrice")),
    ("responsable_scientifique", ("responsable scientifique", "president du comite scientifique", "presidente du comite scientifique", "general chair", "chair", "coordonnateur", "رئيس اللجنة العلمية")),
    ("comite_scientifique", ("comite scientifique", "scientific committee", "comite scientifique international", "اللجنة العلمية")),
    ("comite_organisation", ("comite d organisation", "comite organisateur", "organizing committee", "اللجنة التنظيمية")),
    ("intervenants", ("intervenants", "conferenciers", "conferenciers invites", "keynote", "keynote speakers", "invited speakers", "المحاضرون")),
    ("participants", ("participants", "nombre de participants", "participation", "المشاركون")),
    ("pays_representes", ("pays representes", "pays participants", "countries", "الدول المشاركة")),
    ("institutions_representees", ("institutions representees", "etablissements participants", "institutions")),
    ("partenaires", ("partenaires", "partenariat", "partners", "الشركاء")),
    ("sponsors", ("sponsors", "sponsoring", "parrainage", "الرعاة")),
    ("financeurs", ("financeurs", "sources de financement", "financement", "funding", "التمويل")),
    ("budget_total", ("budget total", "budget previsionnel", "budget", "cout total", "الميزانية")),
    ("modalites_publication", ("modalites de publication", "publication", "publications", "actes", "proceedings", "النشر")),
    ("livrables", ("livrables", "deliverables", "produits attendus")),
    ("resultats_attendus", ("resultats attendus", "expected results", "النتائج المنتظرة")),
    ("retombees_scientifiques", ("retombees scientifiques", "impact scientifique")),
    ("retombees_doctorales", ("retombees doctorales", "formation doctorale", "doctorants")),
    ("retombees_socio_economiques", ("retombees socio economiques", "impact socio economique", "retombees socio-economiques")),
    ("references_reglementaires", ("references reglementaires", "textes de reference", "cadre reglementaire")),
)

DATE_NUMERIC = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")
DATE_TEXTUAL = re.compile(
    r"\b(\d{1,2})(?:\s*(?:er|ème|eme|st|nd|rd|th))?\s+([A-Za-zÀ-ÿ؀-ۿ]{3,12})\.?\s+(\d{4})\b"
)
AMOUNT = re.compile(
    r"\b(\d{1,3}(?:[  .,]\d{3})+|\d{4,})\s*(DA|DZD|dinars?|€|EUR|euros?|USD|\$|دج|دينار)\b",
    re.IGNORECASE,
)
#: Une référence peut mêler chiffres, lettres et séparateurs : « 595/SG »,
#: « 218/DCEU-SDPUR », « 18-07 ». Le motif accepte ces formes puis la date.
REGULATION_REF = re.compile(
    r"\b(?:loi|ordonnance|decret|décret|arrete|arrêté|envoi|circulaire|instruction|note)\s+"
    r"n\s*[°ºo]?\s*\d[\w\-/]*"
    r"(?:\s+du\s+\d{1,2}(?:\s*(?:er|ème|eme))?\s+[A-Za-zÀ-ÿ]+\s+\d{4})?",
    re.IGNORECASE,
)
COUNT_PATTERN = re.compile(r"\b(\d{1,4})\s+(?:pays|countries|دول)\b", re.IGNORECASE)


# --------------------------------------------------------------------------
# Résultat d'extraction
# --------------------------------------------------------------------------


@dataclass
class Extraction:
    key: str
    value: str
    page_no: int
    excerpt: str
    confidence: float
    method: str


@dataclass
class ExtractionReport:
    extractions: list[Extraction] = field(default_factory=list)
    #: Observations objectives réutilisées par les contrôles automatiques.
    observations: dict[str, object] = field(default_factory=dict)

    def add(self, extraction: Extraction) -> None:
        self.extractions.append(extraction)


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------


def _strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


#: Apostrophes remplacées par une espace — substitution 1 pour 1, qui préserve
#: l'alignement des positions avec le texte original.
_APOSTROPHES = str.maketrans("'\u2019\u2018\u02bc", "    ")


def _searchable(text: str) -> str:
    """Texte minuscule, sans accent ni apostrophe, aligné sur l'original.

    L'apostrophe est neutralisée pour que « comité d'organisation » et
    « comite d organisation » se correspondent, sans décaler les index.
    """
    return _strip_accents(text).lower().translate(_APOSTROPHES)


def _excerpt(text: str, start: int, end: int) -> str:
    left = max(0, start - EXCERPT_WIDTH // 3)
    right = min(len(text), end + EXCERPT_WIDTH)
    prefix = "… " if left > 0 else ""
    suffix = " …" if right < len(text) else ""
    return f"{prefix}{' '.join(text[left:right].split())}{suffix}"


def _clean_value(value: str) -> str:
    value = " ".join(value.split())
    value = value.strip(" \t:;.-–—•*")
    return value[:MAX_VALUE_LENGTH]


def _parse_date(match: re.Match, textual: bool) -> str | None:
    """Retourne une date normalisée JJ/MM/AAAA, ou None si elle est invalide."""
    try:
        if textual:
            day = int(match.group(1))
            month_key = _strip_accents(match.group(2)).lower()
            month = MONTHS.get(month_key) or MONTHS.get(month_key[:4]) or MONTHS.get(month_key[:3])
            year = int(match.group(3))
            if month is None:
                return None
        else:
            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if not (1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100):
            return None
        return f"{day:02d}/{month:02d}/{year}"
    except (ValueError, IndexError):
        return None


def _amount_to_int(raw: str) -> int | None:
    digits = re.sub(r"[^\d]", "", raw)
    return int(digits) if digits else None


# --------------------------------------------------------------------------
# Extracteurs
# --------------------------------------------------------------------------


def _extract_labelled(report: ExtractionReport, page_no: int, text: str) -> None:
    """Valeur suivant un libellé explicite : « Lieu : Campus X »."""
    haystack = _searchable(text)
    for key, labels in LABELLED_FIELDS:
        for label in labels:
            needle = _strip_accents(label).lower().translate(_APOSTROPHES)
            for match in re.finditer(
                r"(?:^|[\n\r•\-–—|])\s*" + re.escape(needle) + r"\s*[:：\-–—]\s*",
                haystack,
                flags=re.MULTILINE,
            ):
                start = match.end()
                # La valeur s'arrête à la fin de ligne, ou au libellé suivant.
                end = haystack.find("\n", start)
                end = len(text) if end == -1 else end
                value = _clean_value(text[start:end])
                if len(value) < 2:
                    continue
                report.add(
                    Extraction(
                        key=key,
                        value=value,
                        page_no=page_no,
                        excerpt=_excerpt(text, match.start(), end),
                        confidence=CONFIDENCE_LABELLED,
                        method=f"libellé « {label} »",
                    )
                )
                break


def _extract_dates(report: ExtractionReport, page_no: int, text: str) -> None:
    found: list[tuple[str, int, int]] = []
    for match in DATE_NUMERIC.finditer(text):
        parsed = _parse_date(match, textual=False)
        if parsed:
            found.append((parsed, match.start(), match.end()))
    for match in DATE_TEXTUAL.finditer(text):
        parsed = _parse_date(match, textual=True)
        if parsed:
            found.append((parsed, match.start(), match.end()))

    if not found:
        return
    found.sort(key=lambda item: item[1])
    report.observations.setdefault("dates", []).extend(
        {"value": value, "page": page_no, "excerpt": _excerpt(text, start, end)}
        for value, start, end in found
    )

    # « du X au Y » identifie explicitement un début et une fin.
    haystack = _searchable(text)
    for match in re.finditer(r"\bdu\b(.{0,80}?)\bau\b(.{0,60})", haystack, flags=re.DOTALL):
        window = text[match.start() : match.end()]
        inner = [value for value, start, end in found if match.start() <= start < match.end()]
        if len(inner) >= 2:
            for key, value in (("date_debut", inner[0]), ("date_fin", inner[-1])):
                report.add(
                    Extraction(
                        key=key,
                        value=value,
                        page_no=page_no,
                        excerpt=_excerpt(text, match.start(), match.end()),
                        confidence=CONFIDENCE_PATTERN,
                        method="intervalle « du … au … »",
                    )
                )
            return
        del window

    report.add(
        Extraction(
            key="date_debut",
            value=found[0][0],
            page_no=page_no,
            excerpt=_excerpt(text, found[0][1], found[0][2]),
            confidence=CONFIDENCE_HEURISTIC,
            method="première date rencontrée",
        )
    )


def _extract_event_kind(report: ExtractionReport, page_no: int, text: str) -> None:
    haystack = _searchable(text)
    for kind in EVENT_KINDS:
        needle = _strip_accents(kind).lower()
        index = haystack.find(needle)
        if index == -1:
            continue
        report.add(
            Extraction(
                key="type_manifestation",
                value=kind,
                page_no=page_no,
                excerpt=_excerpt(text, index, index + len(needle)),
                confidence=CONFIDENCE_PATTERN,
                method="vocabulaire des types de manifestation",
            )
        )
        return


def _extract_format(report: ExtractionReport, page_no: int, text: str) -> None:
    haystack = _searchable(text)
    for term, label in FORMAT_TERMS.items():
        needle = _strip_accents(term).lower()
        index = haystack.find(needle)
        if index == -1:
            continue
        report.add(
            Extraction(
                key="format",
                value=label,
                page_no=page_no,
                excerpt=_excerpt(text, index, index + len(needle)),
                confidence=CONFIDENCE_PATTERN,
                method=f"terme « {term} »",
            )
        )
        return


def _extract_institutions(report: ExtractionReport, page_no: int, text: str) -> None:
    haystack = _searchable(text)
    names: list[str] = []
    for prefix in INSTITUTION_PREFIXES:
        needle = _strip_accents(prefix).lower()
        for match in re.finditer(re.escape(needle), haystack):
            start = match.start()
            end = haystack.find("\n", start)
            end = min(len(text), start + 90) if end == -1 else min(end, start + 90)
            name = _clean_value(text[start:end])
            # Coupe sur un séparateur de liste pour ne pas absorber la suite.
            name = re.split(r"\s[;|]\s|\s{3,}", name)[0].strip()
            if not (6 <= len(name) <= 110):
                continue
            key_name = normalize(name)
            # Écarte les quasi-doublons : « Université X » et « Université X, Alger ».
            duplicate = any(
                key_name in normalize(existing) or normalize(existing) in key_name
                for existing in names
            )
            if not duplicate:
                names.append(name)
    if not names:
        return
    report.observations["institutions"] = names
    report.add(
        Extraction(
            key="institutions_representees",
            value=" ; ".join(names[:20]),
            page_no=page_no,
            excerpt=_excerpt(text, haystack.find(_strip_accents(names[0]).lower()), 0)
            if names
            else "",
            confidence=CONFIDENCE_PATTERN,
            method=f"{len(names)} dénomination(s) institutionnelle(s) reconnue(s)",
        )
    )


def _extract_countries(report: ExtractionReport, page_no: int, text: str) -> None:
    normalized = normalize(text)
    found: list[str] = []
    for country in COUNTRIES:
        # Frontières de mots obligatoires : « Inde » ne doit pas correspondre
        # à « indexés », ni « Mali » à « malicieux ».
        if contains_term(normalized, country) is not None and country not in found:
            found.append(country)
    if found:
        existing = report.observations.setdefault("countries", [])
        for country in found:
            if country not in existing:
                existing.append(country)
        report.add(
            Extraction(
                key="pays_representes",
                value=" ; ".join(found),
                page_no=page_no,
                excerpt=f"{len(found)} pays reconnus dans le texte de la page {page_no}.",
                confidence=CONFIDENCE_PATTERN,
                method="liste de pays reconnus",
            )
        )
    for match in COUNT_PATTERN.finditer(text):
        report.observations.setdefault("declared_country_counts", []).append(
            {"count": int(match.group(1)), "page": page_no, "excerpt": _excerpt(text, match.start(), match.end())}
        )


def _extract_amounts(report: ExtractionReport, page_no: int, text: str) -> None:
    amounts: list[dict] = []
    for match in AMOUNT.finditer(text):
        value = _amount_to_int(match.group(1))
        if value is None:
            continue
        currency = CURRENCIES.get(_strip_accents(match.group(2)).lower(), match.group(2).upper())
        amounts.append(
            {
                "value": value,
                "currency": currency,
                "page": page_no,
                "text": _clean_value(match.group(0)),
                "excerpt": _excerpt(text, match.start(), match.end()),
                # Le mot « total » n'est retenu que s'il figure sur la même
                # ligne que le montant : un total en ligne précédente ne doit
                # pas qualifier le montant suivant.
                "is_total": bool(
                    re.search(
                        r"\b(total|montant global|somme|إجمالي)\b",
                        _searchable(text[text.rfind("\n", 0, match.start()) + 1 : match.start()]),
                    )
                ),
            }
        )
    if not amounts:
        return
    report.observations.setdefault("amounts", []).extend(amounts)
    report.add(
        Extraction(
            key="montants_devise",
            value=" ; ".join(f"{item['value']} {item['currency']}" for item in amounts[:15]),
            page_no=page_no,
            excerpt=amounts[0]["excerpt"],
            confidence=CONFIDENCE_PATTERN,
            method=f"{len(amounts)} montant(s) détecté(s)",
        )
    )
    totals = [item for item in amounts if item["is_total"]]
    if totals:
        report.add(
            Extraction(
                key="budget_total",
                value=f"{totals[0]['value']} {totals[0]['currency']}",
                page_no=page_no,
                excerpt=totals[0]["excerpt"],
                confidence=CONFIDENCE_LABELLED,
                method="montant précédé du mot « total »",
            )
        )


def _extract_regulations(report: ExtractionReport, page_no: int, text: str) -> None:
    refs = []
    for match in REGULATION_REF.finditer(text):
        ref = _clean_value(match.group(0))
        if ref not in refs:
            refs.append(ref)
    if refs:
        report.add(
            Extraction(
                key="references_reglementaires",
                value=" ; ".join(refs[:12]),
                page_no=page_no,
                excerpt=_excerpt(text, *_first_span(REGULATION_REF, text)),
                confidence=CONFIDENCE_PATTERN,
                method="références réglementaires citées dans le texte",
            )
        )


def _first_span(pattern: re.Pattern, text: str) -> tuple[int, int]:
    match = pattern.search(text)
    return (match.start(), match.end()) if match else (0, 0)


def _extract_title(report: ExtractionReport, page_no: int, text: str) -> None:
    """Titre déduit de la première ligne significative de la première page."""
    if page_no != 1:
        return
    for line in text.splitlines():
        candidate = _clean_value(line)
        if len(candidate) < 15 or len(candidate) > 220:
            continue
        if not any(char.isalpha() for char in candidate):
            continue
        report.add(
            Extraction(
                key="intitule",
                value=candidate,
                page_no=page_no,
                excerpt=_excerpt(text, text.find(line), text.find(line) + len(line)),
                confidence=CONFIDENCE_HEURISTIC,
                method="première ligne significative de la page 1",
            )
        )
        return


PAGE_EXTRACTORS = (
    _extract_labelled,
    _extract_dates,
    _extract_event_kind,
    _extract_format,
    _extract_institutions,
    _extract_countries,
    _extract_amounts,
    _extract_regulations,
    _extract_title,
)


def analyze_text(pages: dict[int, str]) -> ExtractionReport:
    """Analyse tout le texte disponible et retourne les valeurs proposées."""
    report = ExtractionReport()
    for page_no in sorted(pages):
        text = pages[page_no]
        if not text or not text.strip():
            continue
        for extractor in PAGE_EXTRACTORS:
            extractor(report, page_no, text)
    return report


def best_per_field(report: ExtractionReport) -> dict[str, Extraction]:
    """Retient, pour chaque champ, la proposition la plus fiable puis la plus précoce."""
    best: dict[str, Extraction] = {}
    for extraction in report.extractions:
        current = best.get(extraction.key)
        if current is None:
            best[extraction.key] = extraction
            continue
        if (extraction.confidence, -extraction.page_no) > (current.confidence, -current.page_no):
            best[extraction.key] = extraction
    return best


# --------------------------------------------------------------------------
# Persistance
# --------------------------------------------------------------------------


def autofill_dossier(session: Session, dossier_id: str) -> dict:
    """Renseigne les informations du dossier à partir du texte extrait.

    Ne touche jamais un champ déjà qualifié par l'évaluateur : une valeur
    confirmée, corrigée, rejetée ou déclarée non applicable est conservée.
    """
    settings = get_settings()
    key = get_master_key()
    pages = dossier_service.dossier_page_texts(session, dossier_id)
    report = analyze_text(pages)
    proposals = best_per_field(report)

    items = {
        item.key: item
        for item in session.scalars(
            select(ExtractedItem).where(ExtractedItem.dossier_id == dossier_id)
        ).all()
    }

    human_qualified = {
        InformationStatus.CONFIRME,
        InformationStatus.CORRIGE,
        InformationStatus.REJETE,
        InformationStatus.NON_APPLICABLE,
    }

    filled, skipped = 0, 0
    for field_key, extraction in proposals.items():
        item = items.get(field_key)
        if item is None:
            continue
        if item.status in human_qualified:
            skipped += 1
            continue

        item.current_value_cipher = encrypt_text(
            key, extraction.value, dossier_service.item_aad(item.id, "current")
        )
        if item.initial_value_cipher is None:
            item.initial_value_cipher = encrypt_text(
                key, extraction.value, dossier_service.item_aad(item.id, "initial")
            )
        item.source_cipher = encrypt_text(
            key,
            f"{extraction.excerpt}\n[détection : {extraction.method}]",
            dossier_service.item_aad(item.id, "source"),
        )
        item.page_no = extraction.page_no
        item.confidence = extraction.confidence
        item.extraction_mode = ExtractionMode.NATIF
        # Statut inchangé : la valeur est proposée, jamais confirmée.
        item.status = InformationStatus.A_VERIFIER
        item.manual_entry_validated = False
        item.updated_by = "Extraction automatique"
        filled += 1

    audit.record(
        session,
        audit.AuditAction.ITEM_CORRECTION,
        f"Extraction automatique : {filled} information(s) proposée(s) au statut A_VERIFIER, "
        f"{skipped} champ(s) déjà qualifié(s) par l'évaluateur préservé(s).",
        entity_type="dossier",
        entity_id=dossier_id,
        dossier_id=dossier_id,
        fingerprint=value_fingerprint(",".join(sorted(proposals))),
        actor_label=settings.evaluator_label,
    )
    session.commit()

    return {
        "proposed": filled,
        "preserved": skipped,
        "fields": sorted(proposals),
        "observations": report.observations,
        "notice": (
            "Toutes les valeurs sont proposées au statut A_VERIFIER avec leur page et leur "
            "extrait source. Aucune n'est confirmée : la confirmation appartient à l'évaluateur."
        ),
    }
