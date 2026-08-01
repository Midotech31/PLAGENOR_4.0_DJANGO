"""Application déterministe des 26 critères réglementaires.

Chaque critère reçoit obligatoirement un statut — `C`, `PC`, `NC` ou `NV` —
accompagné d'un constat, de ses preuves et du fondement exact. **Aucune cellule
n'est jamais laissée vide.**

Règles impératives appliquées ici :

* aucun délai universel de six mois n'existe ni n'est appliqué ;
* `I2` comporte une exception bilatérale ;
* `I7` affiche le ratio exact sans marge de tolérance inventée ;
* `I9` porte « si possible » et ne peut pas devenir un seuil bloquant ;
* une information absente produit `NV`, jamais une supposition.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from app.core.config import PROJECT_DIR
from app.core.text import contains_term, normalize

REFERENTIAL_FILE = PROJECT_DIR / "rules" / "referentiel_26_criteres.json"

#: Continents des pays reconnus — sert au calcul de `I2`, jamais à conclure.
CONTINENTS: dict[str, str] = {
    "algérie": "Afrique", "algeria": "Afrique", "maroc": "Afrique", "morocco": "Afrique",
    "tunisie": "Afrique", "tunisia": "Afrique", "libye": "Afrique", "libya": "Afrique",
    "égypte": "Afrique", "egypt": "Afrique", "sénégal": "Afrique", "senegal": "Afrique",
    "mali": "Afrique", "niger": "Afrique", "mauritanie": "Afrique", "nigeria": "Afrique",
    "afrique du sud": "Afrique", "south africa": "Afrique",
    "france": "Europe", "espagne": "Europe", "spain": "Europe", "italie": "Europe",
    "italy": "Europe", "allemagne": "Europe", "germany": "Europe", "belgique": "Europe",
    "belgium": "Europe", "suisse": "Europe", "switzerland": "Europe", "portugal": "Europe",
    "royaume-uni": "Europe", "united kingdom": "Europe", "pays-bas": "Europe",
    "netherlands": "Europe", "pologne": "Europe", "poland": "Europe", "roumanie": "Europe",
    "romania": "Europe", "grèce": "Europe", "greece": "Europe", "russie": "Europe",
    "turquie": "Europe", "turkey": "Europe",
    "canada": "Amérique", "états-unis": "Amérique", "united states": "Amérique",
    "brésil": "Amérique", "brazil": "Amérique",
    "arabie saoudite": "Asie", "saudi arabia": "Asie", "jordanie": "Asie", "jordan": "Asie",
    "liban": "Asie", "lebanon": "Asie", "qatar": "Asie", "émirats arabes unis": "Asie",
    "malaisie": "Asie", "malaysia": "Asie", "chine": "Asie", "china": "Asie",
    "japon": "Asie", "japan": "Asie", "inde": "Asie", "india": "Asie",
}

#: Termes signalant une coopération bilatérale — exception explicite de `I2`.
BILATERAL_TERMS = (
    "coopération bilatérale", "cooperation bilaterale", "accord bilatéral",
    "projet bilatéral", "bilateral cooperation", "bilateral agreement",
    "projet de recherche conjoint", "joint project", "تعاون ثنائي",
)


class Status:
    C = "C"
    PC = "PC"
    NC = "NC"
    NV = "NV"


@dataclass
class CriterionResult:
    code: str
    label: str
    family: str
    order: int
    status: str
    finding: str
    exact_source: str
    page: str
    nature: str
    blocking: bool
    evidence_ids: list[str] = field(default_factory=list)
    calculation: dict | None = None
    note: str | None = None


@lru_cache(maxsize=1)
def load_referential() -> dict:
    if not REFERENTIAL_FILE.exists():
        raise FileNotFoundError(
            "rules/referentiel_26_criteres.json est absent : aucun constat réglementaire "
            "ne peut être produit."
        )
    return json.loads(REFERENTIAL_FILE.read_text(encoding="utf-8"))


def clear_cache() -> None:
    load_referential.cache_clear()


@dataclass
class DossierFacts:
    """Faits observés, tous issus de l'extraction locale et sourcés."""

    values: dict[str, str] = field(default_factory=dict)
    pages: dict[int, str] = field(default_factory=dict)
    observations: dict = field(default_factory=dict)
    pieces: dict[str, str] = field(default_factory=dict)
    findings: list[dict] = field(default_factory=list)
    evidence: dict[str, str] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return "\n".join(self.pages[page] for page in sorted(self.pages))

    def has_term(self, term: str) -> int | None:
        """Retourne la page où le terme apparaît, ou None."""
        for page_no in sorted(self.pages):
            if contains_term(normalize(self.pages[page_no]), term) is not None:
                return page_no
        return None

    def evidence_for(self, page_no: int | None) -> list[str]:
        if page_no is None:
            return []
        key = self.evidence.get(f"page:{page_no}")
        return [key] if key else []


# --------------------------------------------------------------------------
# Calculs par type
# --------------------------------------------------------------------------


def _pieces_presence(criterion: dict, facts: DossierFacts) -> tuple[str, str, dict]:
    required = criterion["calculation_params"]["required"]
    confirmed, detected, absent = [], [], []
    for key in required:
        status = facts.pieces.get(key, "ABSENTE")
        if status == "CONFIRMEE":
            confirmed.append(key)
        elif status in {"DETECTEE", "A_VERIFIER", "INCOMPLETE"}:
            detected.append(key)
        else:
            absent.append(key)

    calculation = {"confirmees": confirmed, "reperees": detected, "non_reperees": absent}
    if absent and not detected and not confirmed:
        return (
            Status.NC,
            f"Aucune des {len(required)} pièces requises n'a été repérée : "
            f"{', '.join(absent)}.",
            calculation,
        )
    if absent:
        return (
            Status.NC,
            f"{len(absent)} pièce(s) requise(s) non repérée(s) : {', '.join(absent)}. "
            f"Repérées : {', '.join(confirmed + detected) or 'aucune'}.",
            calculation,
        )
    if confirmed and not detected:
        return (
            Status.C,
            f"Les {len(required)} pièces requises sont confirmées par l'évaluateur.",
            calculation,
        )
    return (
        Status.PC,
        f"Les {len(required)} pièces sont repérées textuellement mais "
        f"{len(detected)} restent à confirmer : {', '.join(detected)}. Le repérage d'un "
        "titre ne vaut pas confirmation de la validité de la pièce.",
        calculation,
    )


def _deposit_lead_time(criterion: dict, facts: DossierFacts) -> tuple[str, str, dict]:
    minimum = criterion["calculation_params"]["minimum_days"]
    start = _parse_date(facts.values.get("date_debut"))
    deposit = _parse_date(facts.values.get("date_depot"))
    calculation = {
        "minimum_jours": minimum,
        "date_ouverture": facts.values.get("date_debut"),
        "date_depot": facts.values.get("date_depot"),
        "regle": "Dépôt au moins 10 jours avant la session régionale compétente.",
        "delai_six_mois_applique": False,
    }
    if start is None or deposit is None:
        return (
            Status.NV,
            "La date de dépôt régional ou la date d'ouverture n'est pas documentée : le "
            f"délai minimal de {minimum} jours avant la session régionale n'est pas "
            "calculable. Aucun délai de six mois n'est applicable.",
            calculation,
        )
    delta = (start - deposit).days
    calculation["ecart_jours"] = delta
    if delta >= minimum:
        return (
            Status.C,
            f"Dépôt le {facts.values['date_depot']} pour une ouverture le "
            f"{facts.values['date_debut']} : {delta} jours, soit au moins {minimum} jours.",
            calculation,
        )
    return (
        Status.NC,
        f"Dépôt le {facts.values['date_depot']} pour une ouverture le "
        f"{facts.values['date_debut']} : {delta} jours, inférieur au minimum de "
        f"{minimum} jours avant la session régionale.",
        calculation,
    )


def _presential_share(criterion: dict, facts: DossierFacts) -> tuple[str, str, dict]:
    minimum = criterion["calculation_params"]["minimum_ratio"]
    mode = (facts.values.get("format") or "").lower()
    ratio = facts.observations.get("presential_ratio")
    calculation = {"mode_declare": facts.values.get("format"), "seuil_hybride": minimum,
                   "part_presentielle": ratio}

    if not mode:
        return (
            Status.NV,
            "Le mode d'organisation n'est pas documenté : ni le caractère présentiel ni la "
            "part présentielle d'un éventuel mode hybride ne sont vérifiables.",
            calculation,
        )
    if "présentiel" in mode or "presentiel" in mode:
        return (
            Status.C,
            "Le mode déclaré est présentiel, conformément à la préférence du référentiel.",
            calculation,
        )
    if "hybride" in mode:
        if ratio is None:
            return (
                Status.NV,
                "Mode hybride déclaré, mais la part présentielle n'est pas documentée : le "
                f"seuil de {int(minimum * 100)} % n'est pas vérifiable.",
                calculation,
            )
        if ratio >= minimum:
            return (
                Status.C,
                f"Mode hybride avec une part présentielle documentée de {ratio:.0%}, "
                f"au moins égale au seuil de {int(minimum * 100)} %.",
                calculation,
            )
        return (
            Status.NC,
            f"Mode hybride avec une part présentielle de {ratio:.0%}, inférieure au seuil "
            f"de {int(minimum * 100)} %.",
            calculation,
        )
    return (
        Status.NC,
        f"Le mode déclaré « {facts.values.get('format')} » n'est ni présentiel ni hybride : "
        "le référentiel privilégie le présentiel.",
        calculation,
    )


def _restricted_piece(criterion: dict, facts: DossierFacts) -> tuple[str, str, dict]:
    key = criterion["calculation_params"]["piece"]
    status = facts.pieces.get(key, "ABSENTE")
    calculation = {"piece": key, "statut": status,
                   "confidentialite": "Seule la présence est contrôlée ; aucune donnée de "
                                      "passeport n'est reproduite."}
    if status == "CONFIRMEE":
        return (Status.C, "La liste des conférenciers étrangers et les copies de passeports "
                          "sont présentes en section restreinte, confirmées par l'évaluateur.",
                calculation)
    if status in {"DETECTEE", "A_VERIFIER", "INCOMPLETE"}:
        return (Status.PC, "La pièce est repérée en section restreinte mais n'est pas encore "
                           "confirmée. Aucune donnée de passeport n'est exploitée.", calculation)
    return (Status.NC, "La liste des conférenciers étrangers et les copies de passeports ne "
                       "sont pas repérées au dossier.", calculation)


def _country_continent_coverage(criterion: dict, facts: DossierFacts) -> tuple[str, str, dict]:
    params = criterion["calculation_params"]
    countries = facts.observations.get("countries") or []
    continents = sorted({CONTINENTS[normalize(c)] for c in countries if normalize(c) in CONTINENTS})
    calculation = {
        "pays": countries,
        "nombre_pays": len(countries),
        "continents": continents,
        "nombre_continents": len(continents),
        "seuil_pays": params["min_countries"],
        "seuil_continents": params["min_continents"],
    }

    if params.get("bilateral_exception"):
        for term in BILATERAL_TERMS:
            page = facts.has_term(term)
            if page is not None:
                calculation["exception_bilaterale"] = {"terme": term, "page": page}
                return (
                    Status.PC,
                    f"Une coopération bilatérale est mentionnée page {page} (« {term} ») : "
                    "l'exception prévue par le référentiel peut s'appliquer et le seuil de "
                    f"{params['min_countries']} pays / {params['min_continents']} continents "
                    "n'est pas opposable en l'état. Pays reconnus : "
                    f"{', '.join(countries) or 'aucun'}.",
                    calculation,
                )

    if not countries:
        return (
            Status.NV,
            "Aucun pays n'est nommément identifiable dans les affiliations : la couverture "
            f"de {params['min_countries']} pays et {params['min_continents']} continents "
            "n'est pas calculable.",
            calculation,
        )
    if len(countries) >= params["min_countries"] and len(continents) >= params["min_continents"]:
        return (
            Status.C,
            f"{len(countries)} pays ({', '.join(countries)}) et {len(continents)} continents "
            f"({', '.join(continents)}) sont identifiés, au moins égaux aux seuils requis.",
            calculation,
        )
    return (
        Status.NC,
        f"{len(countries)} pays ({', '.join(countries)}) et {len(continents)} continents "
        f"identifiés, en deçà des {params['min_countries']} pays et "
        f"{params['min_continents']} continents requis.",
        calculation,
    )


def _ratio_threshold(criterion: dict, facts: DossierFacts) -> tuple[str, str, dict]:
    params = criterion["calculation_params"]
    numerator = facts.observations.get(params["numerator"])
    denominator = facts.observations.get(params["denominator"])
    calculation = {
        "numerateur": numerator,
        "denominateur": denominator,
        "seuil": params["minimum_ratio"],
    }
    if not denominator:
        return (
            Status.NV,
            "Le nombre total de membres du comité n'est pas documenté nominativement : la "
            f"proportion internationale de {int(params['minimum_ratio'] * 100)} % n'est pas "
            "calculable.",
            calculation,
        )
    ratio = (numerator or 0) / denominator
    calculation["ratio"] = round(ratio, 4)
    if ratio >= params["minimum_ratio"]:
        return (
            Status.C,
            f"{numerator}/{denominator} membres affiliés à l'étranger, soit {ratio:.1%}, "
            f"au moins égal au seuil de {int(params['minimum_ratio'] * 100)} %.",
            calculation,
        )
    return (
        Status.NC,
        f"{numerator}/{denominator} membres affiliés à l'étranger, soit {ratio:.1%}, "
        f"inférieur au seuil de {int(params['minimum_ratio'] * 100)} %.",
        calculation,
    )


def _ratio_approximate(criterion: dict, facts: DossierFacts) -> tuple[str, str, dict]:
    """`I7` : « environ 10 % ». Le ratio exact est affiché, sans tolérance inventée."""
    params = criterion["calculation_params"]
    numerator = facts.observations.get(params["numerator"])
    denominator = facts.observations.get(params["denominator"])
    calculation = {
        "numerateur": numerator,
        "denominateur": denominator,
        "ratio_reference": params["reference_ratio"],
        "tolerance": None,
        "libelle_source": "environ 10 %",
    }
    if not denominator:
        return (
            Status.NV,
            "Le nombre d'intervenants n'est pas documenté nominativement : le ratio "
            "d'intervenants internationaux présents physiquement n'est pas calculable. Le "
            "référentiel dit « environ 10 % » ; aucune marge de tolérance n'est inventée.",
            calculation,
        )
    ratio = (numerator or 0) / denominator
    calculation["ratio"] = round(ratio, 4)
    return (
        Status.PC,
        f"Ratio exact calculé : {numerator}/{denominator} = {ratio:.1%}. Le référentiel "
        "indique « environ 10 % » sans marge chiffrée : l'appréciation de cette proximité "
        "revient à l'évaluateur, l'application ne tranche pas.",
        calculation,
    )


def _keyword_evidence(criterion: dict, facts: DossierFacts) -> tuple[str, str, dict]:
    terms = criterion["calculation_params"]["terms"]
    hits = []
    for term in terms:
        page = facts.has_term(term)
        if page is not None:
            hits.append({"terme": term, "page": page})
    calculation = {"termes_recherches": terms, "occurrences": hits}
    if hits:
        listed = ", ".join(f"« {h['terme'] } » p. {h['page']}" for h in hits[:4])
        return (
            Status.PC,
            f"Mention repérée dans le dossier : {listed}. Une mention textuelle atteste "
            "l'annonce, non sa réalisation : la confirmation revient à l'évaluateur.",
            calculation,
        )
    # Le constat reste court ; la liste complète des termes cherchés est
    # conservée dans le calcul, consultable preuve à l'appui.
    listed_terms = ", ".join(terms[:3])
    if len(terms) > 3:
        listed_terms += f" et {len(terms) - 3} autre(s)"
    return (
        Status.NC,
        f"Aucune mention correspondante dans le texte extrait ({listed_terms}).",
        calculation,
    )


def _url_evidence(criterion: dict, facts: DossierFacts) -> tuple[str, str, dict]:
    import re

    urls = re.findall(r"https?://[^\s,;)\]]+", facts.full_text)
    calculation = {"urls": urls[:10], "nombre": len(urls)}
    if not urls:
        return (
            Status.NC,
            "Aucune adresse de site n'a été repérée dans le dossier.",
            calculation,
        )
    institutional = [u for u in urls if any(token in u.lower() for token in (".dz", ".edu", "univ", "ac."))]
    calculation["institutionnelles"] = institutional
    if institutional:
        return (
            Status.PC,
            f"{len(institutional)} adresse(s) à caractère institutionnel repérée(s) : "
            f"{', '.join(institutional[:3])}. L'existence effective et le caractère dédié du "
            "site restent à vérifier.",
            calculation,
        )
    return (
        Status.PC,
        f"{len(urls)} adresse(s) repérée(s), sans marqueur institutionnel évident : "
        f"{', '.join(urls[:3])}. Le caractère officiel et dédié reste à vérifier.",
        calculation,
    )


def _qualitative_evidence(criterion: dict, facts: DossierFacts) -> tuple[str, str, dict]:
    fields = criterion["calculation_params"]["fields"]
    present = {key: facts.values[key] for key in fields if facts.values.get(key)}
    calculation = {"champs_attendus": fields, "champs_documentes": sorted(present)}
    if not present:
        return (
            Status.NV,
            "Les éléments nécessaires ne sont pas documentés dans le dossier "
            f"(champs attendus : {', '.join(fields)}) : l'appréciation n'est pas possible.",
            calculation,
        )
    if len(present) < len(fields):
        missing = [key for key in fields if key not in present]
        return (
            Status.PC,
            "Éléments partiellement documentés : "
            + " ; ".join(f"{k} = {v[:80]}" for k, v in present.items())
            + f". Manquants : {', '.join(missing)}. L'appréciation de fond revient à "
            "l'évaluateur.",
            calculation,
        )
    return (
        Status.PC,
        "Éléments documentés : "
        + " ; ".join(f"{k} = {v[:80]}" for k, v in present.items())
        + ". La présence de l'information ne vaut pas appréciation de sa qualité : "
        "celle-ci revient à l'évaluateur.",
        calculation,
    )


def _evidence_of_consent(criterion: dict, facts: DossierFacts) -> tuple[str, str, dict]:
    terms = ("acceptation", "accord préalable", "lettre d acceptation", "consent",
             "acceptance letter", "engagement signé")
    hits = [{"terme": t, "page": p} for t in terms if (p := facts.has_term(t)) is not None]
    calculation = {"termes_recherches": list(terms), "occurrences": hits}
    if not hits:
        return (
            Status.NC,
            "Aucune acceptation individuelle signée des membres du comité n'a été repérée "
            "au dossier.",
            calculation,
        )
    return (
        Status.PC,
        f"Mention d'accord repérée ({hits[0]['terme']}, p. {hits[0]['page']}), mais le "
        "caractère individuel et signé de chaque acceptation reste à vérifier pièce par pièce.",
        calculation,
    )


def _keynote_verification(criterion: dict, facts: DossierFacts) -> tuple[str, str, dict]:
    speakers = facts.values.get("intervenants")
    profiles = facts.observations.get("web_profiles") or []
    confirmed = [p for p in profiles if p.get("status") in
                 {"SOURCE_OFFICIELLE_TROUVEE", "SOURCES_CONCORDANTES"}]
    calculation = {
        "intervenants_declares": speakers,
        "profils_verifies": len(profiles),
        "profils_confirmes": len(confirmed),
    }
    if not speakers:
        return (
            Status.NV,
            "Aucun conférencier n'est documenté nominativement : la présence d'un keynote "
            "étranger de réputation internationale n'est pas vérifiable.",
            calculation,
        )
    if confirmed:
        return (
            Status.PC,
            f"{len(confirmed)} profil(s) confirmé(s) par source publique sur "
            f"{len(profiles)} vérifié(s). La réputation internationale relève de "
            "l'appréciation de l'évaluateur.",
            calculation,
        )
    if profiles:
        return (
            Status.PC,
            f"{len(profiles)} profil(s) recherché(s) sans confirmation par source officielle. "
            "Intervenants déclarés : "
            f"{speakers[:120]}.",
            calculation,
        )
    return (
        Status.NV,
        f"Conférenciers déclarés ({speakers[:120]}) mais aucune vérification publique n'a été "
        "menée : la réputation internationale n'est pas établie.",
        calculation,
    )


def _vigilance_review(criterion: dict, facts: DossierFacts) -> tuple[str, str, dict]:
    categories = criterion["calculation_params"]["blocking_categories"]
    relevant = [f for f in facts.findings if f.get("category") in categories]
    confirmed = [f for f in relevant if f.get("human_status") == "CONFIRME"]
    calculation = {
        "categories_surveillees": categories,
        "alertes": len(relevant),
        "alertes_confirmees": len(confirmed),
    }
    if confirmed:
        return (
            Status.NC,
            f"{len(confirmed)} alerte(s) confirmée(s) par l'évaluateur dans les catégories "
            f"surveillées : un contrôle préalable au regard des constantes et valeurs "
            "nationales est requis avant toute suite.",
            calculation,
        )
    if relevant:
        return (
            Status.PC,
            f"{len(relevant)} point(s) de vigilance détecté(s) et non encore qualifié(s) : "
            "le contrôle préalable ne peut pas être considéré comme effectué.",
            calculation,
        )
    return (
        Status.PC,
        "Aucun point de vigilance n'a été détecté par le moteur textuel dans les catégories "
        "surveillées. L'absence d'alerte ne prouve pas l'absence de risque : cartes, "
        "drapeaux, logos et images ne sont pas analysés.",
        calculation,
    )


def _budget_consistency(criterion: dict, facts: DossierFacts) -> tuple[str, str, dict]:
    amounts = facts.observations.get("amounts") or []
    sources = facts.values.get("financeurs")
    calculation = {"montants": len(amounts), "sources_financement": sources}
    if not amounts:
        return (
            Status.NC,
            "Aucun montant n'a été repéré : le budget, ses sources et ses modes de "
            "financement ne sont pas documentés.",
            calculation,
        )
    totals = [a for a in amounts if a["is_total"]]
    others = [a for a in amounts if not a["is_total"]]
    if totals and others:
        total = totals[0]
        same = [a for a in others if a["currency"] == total["currency"]]
        computed = sum(a["value"] for a in same)
        calculation.update({
            "total_declare": f"{total['value']} {total['currency']}",
            "somme_calculee": f"{computed} {total['currency']}",
            "ecart": abs(computed - total["value"]),
        })
        if computed != total["value"]:
            return (
                Status.NC,
                f"Incohérence arithmétique : total déclaré {total['value']} "
                f"{total['currency']}, somme des autres montants {computed} "
                f"{total['currency']}, écart {abs(computed - total['value'])} "
                f"{total['currency']}."
                + ("" if sources else " Les sources de financement ne sont pas documentées."),
                calculation,
            )
    if not sources:
        return (
            Status.PC,
            f"{len(amounts)} montant(s) documenté(s), mais les sources et modes de "
            "financement ne sont pas précisés.",
            calculation,
        )
    return (
        Status.PC,
        f"{len(amounts)} montant(s) et sources de financement documentés "
        f"({sources[:80]}). La soutenabilité du financement relève de l'appréciation de "
        "l'évaluateur.",
        calculation,
    )


CALCULATORS = {
    "PIECES_PRESENCE": _pieces_presence,
    "DEPOSIT_LEAD_TIME": _deposit_lead_time,
    "PRESENTIAL_SHARE": _presential_share,
    "RESTRICTED_PIECE_PRESENCE": _restricted_piece,
    "COUNTRY_CONTINENT_COVERAGE": _country_continent_coverage,
    "RATIO_THRESHOLD": _ratio_threshold,
    "RATIO_APPROXIMATE": _ratio_approximate,
    "KEYWORD_EVIDENCE": _keyword_evidence,
    "URL_EVIDENCE": _url_evidence,
    "QUALITATIVE_EVIDENCE": _qualitative_evidence,
    "EVIDENCE_OF_CONSENT": _evidence_of_consent,
    "KEYNOTE_VERIFICATION": _keynote_verification,
    "VIGILANCE_REVIEW": _vigilance_review,
    "BUDGET_CONSISTENCY": _budget_consistency,
}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        day, month, year = (int(part) for part in value.split("/"))
        return date(year, month, day)
    except (ValueError, AttributeError):
        return None


# --------------------------------------------------------------------------
# Évaluation complète
# --------------------------------------------------------------------------


def evaluate(facts: DossierFacts) -> list[CriterionResult]:
    """Applique les 26 critères, dans l'ordre, sans jamais laisser de cellule vide."""
    referential = load_referential()
    results: list[CriterionResult] = []

    for criterion in sorted(referential["criteria"], key=lambda item: item["order"]):
        if not criterion.get("active", True):
            continue
        calculator = CALCULATORS.get(criterion["calculation"])
        if calculator is None:
            status, finding, calculation = (
                Status.NV,
                "Aucune méthode de calcul n'est définie pour ce critère : statut non "
                "déterminable sans intervention humaine.",
                {},
            )
        else:
            try:
                status, finding, calculation = calculator(criterion, facts)
            except Exception as exc:  # noqa: BLE001 - un échec devient NV, jamais une invention
                status, finding, calculation = (
                    Status.NV,
                    "Le calcul n'a pas pu aboutir sur les données disponibles "
                    f"({type(exc).__name__}) : statut non déterminable.",
                    {},
                )

        # Un critère non bloquant portant « si possible » ne devient jamais NC.
        if not criterion["blocking"] and status == Status.NC and criterion.get("exceptions"):
            status = Status.PC
            finding = (
                f"{finding} Ce critère est explicitement conditionnel « lorsque possible » : "
                "son absence ne constitue pas une non-conformité."
            )

        results.append(
            CriterionResult(
                code=criterion["code"],
                label=criterion["label"],
                family=criterion["family"],
                order=criterion["order"],
                status=status,
                finding=finding,
                exact_source=criterion["exact_source"],
                page=str(criterion["page"]),
                nature=criterion["nature"],
                blocking=bool(criterion["blocking"]),
                calculation=calculation or None,
                note=criterion.get("exceptions"),
            )
        )

    return results


def summarize(results: list[CriterionResult]) -> dict:
    counts = {status: 0 for status in (Status.C, Status.PC, Status.NC, Status.NV)}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    blocking_issues = [
        result for result in results
        if result.blocking and result.status in {Status.NC, Status.NV}
    ]
    return {
        "total": len(results),
        "counts": counts,
        "blocking_issues": [
            {"code": r.code, "label": r.label, "status": r.status, "finding": r.finding}
            for r in blocking_issues
        ],
        "referential_version": load_referential()["referential_version"],
    }
