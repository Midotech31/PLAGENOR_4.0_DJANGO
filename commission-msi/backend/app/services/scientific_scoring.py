"""Score scientifique automatique sur 100 (grille détaillée §9.1 à §9.5).

Le score est **proposé** par l'application à partir des seuls éléments
documentés dans le dossier. Il ne remplace jamais le contrôle réglementaire et
ne vaut pas décision.

Règles appliquées sans exception :

* chaque sous-note s'appuie sur des preuves rattachées (`evidence_ids`) ;
* une information absente vaut zéro au sous-critère, avec la mention
  « non documenté » — ce zéro ne préjuge d'aucune incapacité de l'organisateur ;
* les additions et les plafonds sont recalculés localement ;
* la version de la grille est conservée avec le score.

Aucun modèle génératif n'intervient ici : la même entrée produit toujours la
même sortie, et chaque point attribué est explicable ligne à ligne.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache

from app.core.config import PROJECT_DIR
from app.core.text import contains_term, normalize
from app.services.regulatory_engine import CONTINENTS, DossierFacts

GRID_FILE = PROJECT_DIR / "rules" / "grille_scientifique_detaillee.json"

NOT_DOCUMENTED = "non documenté"


@dataclass
class SubScore:
    """Une sous-note, sa justification brève et ses preuves."""

    family: str
    key: str
    label: str
    score: int
    max: int
    justification: str
    evidence_ids: list[str] = field(default_factory=list)
    method: str = ""
    details: dict = field(default_factory=dict)

    @property
    def documented(self) -> bool:
        return self.score > 0


@dataclass
class FamilyScore:
    key: str
    label: str
    score: int
    max: int
    subscores: list[SubScore]


@dataclass
class ScientificScore:
    total: int
    maximum: int
    grid_version: str
    families: list[FamilyScore]
    notice: str

    @property
    def subscores(self) -> list[SubScore]:
        return [sub for family in self.families for sub in family.subscores]


@lru_cache(maxsize=1)
def load_grid() -> dict:
    if not GRID_FILE.exists():
        raise FileNotFoundError(
            "rules/grille_scientifique_detaillee.json est absent : aucun score ne peut "
            "être proposé."
        )
    return json.loads(GRID_FILE.read_text(encoding="utf-8"))


def clear_cache() -> None:
    load_grid.cache_clear()


# --------------------------------------------------------------------------
# Outils communs
# --------------------------------------------------------------------------


def _find_signals(facts: DossierFacts, signals: list[str]) -> list[dict]:
    """Repère les signaux textuels présents, avec leur page."""
    found: list[dict] = []
    for term in signals:
        page = facts.has_term(term)
        if page is not None:
            found.append({"terme": term, "page": page})
    return found


def _filled_fields(facts: DossierFacts, keys: list[str]) -> list[str]:
    return [key for key in keys if (facts.values.get(key) or "").strip()]


def _pages_evidence(facts: DossierFacts, pages: list[int]) -> list[str]:
    ids: list[str] = []
    for page in sorted(set(pages)):
        ids.extend(facts.evidence_for(page))
    return ids


def _scale(portion: float, maximum: int) -> int:
    """Convertit une couverture 0..1 en points entiers, sans dépasser le plafond."""
    portion = max(0.0, min(1.0, portion))
    return min(maximum, int(round(portion * maximum)))


def _zero(sub: dict, family: str, reason: str) -> SubScore:
    return SubScore(
        family=family,
        key=sub["key"],
        label=sub["label"],
        score=0,
        max=sub["max"],
        justification=f"{NOT_DOCUMENTED} — {reason} L'absence de documentation ne préjuge "
        "d'aucune incapacité réelle de l'organisateur.",
        method=sub["method"],
    )


# --------------------------------------------------------------------------
# Méthodes de notation
# --------------------------------------------------------------------------


def _evidence_levels(sub: dict, family: str, facts: DossierFacts) -> SubScore:
    """Notation graduée par densité de preuves textuelles et champs renseignés."""
    params = sub.get("params") or {}
    signals = params.get("signals") or []
    supporting = params.get("supporting_fields") or []

    hits = _find_signals(facts, signals)
    filled = _filled_fields(facts, supporting)

    if not hits and not filled:
        return _zero(
            sub,
            family,
            "aucun des éléments recherchés n'apparaît dans le dossier "
            f"({len(signals)} formulation(s) testée(s)).",
        )

    signal_part = min(len(hits), 3) / 3
    if supporting:
        coverage = 0.6 * signal_part + 0.4 * (len(filled) / len(supporting))
    else:
        coverage = signal_part

    score = _scale(coverage, sub["max"])
    # Une preuve réelle ne peut jamais être notée zéro par arrondi.
    if score == 0 and (hits or filled):
        score = 1

    detail_terms = ", ".join(f"« {hit['terme'] } » (p. {hit['page']})" for hit in hits[:4])
    detail_fields = ", ".join(filled)
    justification_parts = []
    if detail_terms:
        justification_parts.append(f"éléments repérés : {detail_terms}")
    if detail_fields:
        justification_parts.append(f"champs renseignés : {detail_fields}")

    return SubScore(
        family=family,
        key=sub["key"],
        label=sub["label"],
        score=score,
        max=sub["max"],
        justification="; ".join(justification_parts) + ".",
        evidence_ids=_pages_evidence(facts, [hit["page"] for hit in hits]),
        method=sub["method"],
        details={"occurrences": hits, "champs": filled},
    )


def _program_coherence(sub: dict, family: str, facts: DossierFacts) -> SubScore:
    """Cohérence objectifs / programme / résultats : trois maillons attendus."""
    links = {
        "objectifs": bool((facts.values.get("objectifs") or "").strip()),
        "programme": facts.has_term("programme") is not None
        or facts.has_term("deroulement") is not None,
        "resultats": facts.has_term("resultats attendus") is not None
        or bool((facts.values.get("modalites_publication") or "").strip()),
    }
    present = [name for name, ok in links.items() if ok]
    if not present:
        return _zero(sub, family, "ni objectifs, ni programme, ni résultats attendus repérés.")

    score = _scale(len(present) / len(links), sub["max"])
    missing = [name for name, ok in links.items() if not ok]
    justification = f"maillons documentés : {', '.join(present)}"
    if missing:
        justification += f" ; maillon(s) absent(s) : {', '.join(missing)}"
    return SubScore(
        family=family,
        key=sub["key"],
        label=sub["label"],
        score=score,
        max=sub["max"],
        justification=justification + ".",
        method=sub["method"],
        details=links,
    )


def _country_diversity(sub: dict, family: str, facts: DossierFacts) -> SubScore:
    params = sub.get("params") or {}
    countries = facts.observations.get("countries") or []
    continents = sorted({CONTINENTS[normalize(c)] for c in countries if normalize(c) in CONTINENTS})
    if not countries:
        return _zero(sub, family, "aucun pays n'est nommément identifiable dans le dossier.")

    country_part = min(len(countries) / params.get("full_countries", 5), 1.0)
    continent_part = min(len(continents) / params.get("full_continents", 3), 1.0)
    score = _scale(0.5 * country_part + 0.5 * continent_part, sub["max"])
    score = max(score, 1)
    return SubScore(
        family=family,
        key=sub["key"],
        label=sub["label"],
        score=score,
        max=sub["max"],
        justification=f"{len(countries)} pays identifiés ({', '.join(countries)}) répartis sur "
        f"{len(continents)} continent(s) ({', '.join(continents) or 'non rattachés'}).",
        method=sub["method"],
        details={"pays": countries, "continents": continents},
    )


def _foreign_speakers(sub: dict, family: str, facts: DossierFacts) -> SubScore:
    foreign = facts.observations.get("intervenants_internationaux")
    total = facts.observations.get("intervenants_total")
    presence = facts.has_term("presentiel") is not None or facts.has_term("en presence") is not None
    consent = (
        facts.has_term("accord de participation") is not None
        or facts.has_term("lettre d acceptation") is not None
        or facts.has_term("confirmation de participation") is not None
    )
    if not foreign:
        return _zero(
            sub,
            family,
            "aucun intervenant affilié à l'étranger n'est identifiable nominativement.",
        )

    ratio = (foreign / total) if total else 0.0
    coverage = min(ratio / 0.10, 1.0) if total else 0.4
    coverage = 0.6 * coverage + 0.2 * float(presence) + 0.2 * float(consent)
    score = max(1, _scale(coverage, sub["max"]))
    detail = f"{foreign} intervenant(s) affilié(s) à l'étranger"
    if total:
        detail += f" sur {total} identifiés, soit {ratio:.1%}"
    detail += f" ; présence physique documentée : {'oui' if presence else 'non'}"
    detail += f" ; accord de participation documenté : {'oui' if consent else 'non'}"
    return SubScore(
        family=family,
        key=sub["key"],
        label=sub["label"],
        score=score,
        max=sub["max"],
        justification=detail + ".",
        method=sub["method"],
        details={
            "internationaux": foreign,
            "total": total,
            "ratio": round(ratio, 4) if total else None,
            "presentiel_documente": presence,
            "accord_documente": consent,
        },
    )


def _program_and_mode(sub: dict, family: str, facts: DossierFacts) -> SubScore:
    mode = (facts.values.get("format") or "").strip()
    programme = facts.has_term("programme") is not None
    sessions = (
        facts.has_term("session") is not None
        or facts.has_term("atelier") is not None
        or facts.has_term("conference pleniere") is not None
    )
    checks = {"mode déclaré": bool(mode), "programme": programme, "sessions": sessions}
    present = [name for name, ok in checks.items() if ok]
    if not present:
        return _zero(sub, family, "ni mode d'organisation, ni programme, ni sessions repérés.")
    score = max(1, _scale(len(present) / len(checks), sub["max"]))
    return SubScore(
        family=family,
        key=sub["key"],
        label=sub["label"],
        score=score,
        max=sub["max"],
        justification=f"mode déclaré : {mode or NOT_DOCUMENTED} ; éléments de programme "
        f"documentés : {', '.join(present)}.",
        method=sub["method"],
        details=checks,
    )


def _governance(sub: dict, family: str, facts: DossierFacts) -> SubScore:
    bodies = {
        "responsable scientifique": bool((facts.values.get("responsable_scientifique") or "").strip()),
        "comité scientifique": bool((facts.values.get("comite_scientifique") or "").strip()),
        "comité d'organisation": bool((facts.values.get("comite_organisation") or "").strip()),
    }
    present = [name for name, ok in bodies.items() if ok]
    if not present:
        return _zero(sub, family, "aucune instance de pilotage n'est nommément documentée.")
    score = max(1, _scale(len(present) / len(bodies), sub["max"]))
    missing = [name for name, ok in bodies.items() if not ok]
    justification = f"instances documentées : {', '.join(present)}"
    if missing:
        justification += f" ; absente(s) : {', '.join(missing)}"
    return SubScore(
        family=family,
        key=sub["key"],
        label=sub["label"],
        score=score,
        max=sub["max"],
        justification=justification + ".",
        method=sub["method"],
        details=bodies,
    )


def _schedule_logistics(sub: dict, family: str, facts: DossierFacts) -> SubScore:
    checks = {
        "dates": bool((facts.values.get("date_debut") or "").strip())
        and bool((facts.values.get("date_fin") or "").strip()),
        "lieu": bool((facts.values.get("lieu") or "").strip()),
        "logistique": facts.has_term("hebergement") is not None
        or facts.has_term("restauration") is not None
        or facts.has_term("transport") is not None
        or facts.has_term("logistique") is not None,
    }
    present = [name for name, ok in checks.items() if ok]
    if not present:
        return _zero(sub, family, "ni dates, ni lieu, ni élément logistique repérés.")
    score = max(1, _scale(len(present) / len(checks), sub["max"]))
    return SubScore(
        family=family,
        key=sub["key"],
        label=sub["label"],
        score=score,
        max=sub["max"],
        justification=f"éléments documentés : {', '.join(present)}.",
        method=sub["method"],
        details=checks,
    )


def _budget_quality(sub: dict, family: str, facts: DossierFacts) -> SubScore:
    amounts = facts.observations.get("amounts") or []
    total_declared = [item for item in amounts if item.get("is_total")]
    sources = bool((facts.values.get("financeurs") or "").strip())
    detail_lines = len([item for item in amounts if not item.get("is_total")])
    if not amounts:
        return _zero(sub, family, "aucun montant n'est chiffré dans le dossier.")

    checks = {
        "montant total": bool(total_declared),
        "postes détaillés": detail_lines >= 2,
        "sources de financement": sources,
    }
    present = [name for name, ok in checks.items() if ok]
    score = max(1, _scale(len(present) / len(checks), sub["max"]))
    return SubScore(
        family=family,
        key=sub["key"],
        label=sub["label"],
        score=score,
        max=sub["max"],
        justification=f"{len(amounts)} montant(s) relevé(s) ; éléments documentés : "
        f"{', '.join(present) or 'aucun'}. La soutenabilité du financement relève de "
        "l'appréciation de l'évaluateur.",
        method=sub["method"],
        details={"montants": len(amounts), "postes": detail_lines, **checks},
    )


def _site_platform(sub: dict, family: str, facts: DossierFacts) -> SubScore:
    urls = facts.observations.get("urls") or []
    platform = (
        facts.has_term("plateforme de soumission") is not None
        or facts.has_term("easychair") is not None
        or facts.has_term("sciencesconf") is not None
        or facts.has_term("soumission en ligne") is not None
    )
    if not urls and not platform:
        return _zero(sub, family, "ni site dédié, ni plateforme de soumission repérés.")
    coverage = 0.5 * float(bool(urls)) + 0.5 * float(platform)
    score = max(1, _scale(coverage, sub["max"]))
    return SubScore(
        family=family,
        key=sub["key"],
        label=sub["label"],
        score=score,
        max=sub["max"],
        justification=f"{len(urls)} adresse(s) repérée(s) ; plateforme de soumission "
        f"documentée : {'oui' if platform else 'non'}. Le caractère institutionnel du site "
        "reste à confirmer par l'évaluateur.",
        method=sub["method"],
        details={"urls": urls[:5], "plateforme": platform},
    )


METHODS = {
    "EVIDENCE_LEVELS": _evidence_levels,
    "PROGRAM_COHERENCE": _program_coherence,
    "COUNTRY_DIVERSITY": _country_diversity,
    "FOREIGN_SPEAKERS": _foreign_speakers,
    "PROGRAM_AND_MODE": _program_and_mode,
    "GOVERNANCE": _governance,
    "SCHEDULE_LOGISTICS": _schedule_logistics,
    "BUDGET_QUALITY": _budget_quality,
    "SITE_PLATFORM": _site_platform,
}


# --------------------------------------------------------------------------
# Notation complète
# --------------------------------------------------------------------------


def score(facts: DossierFacts) -> ScientificScore:
    """Applique la grille détaillée et retourne un score recalculé localement."""
    grid = load_grid()
    families: list[FamilyScore] = []

    for family in grid["families"]:
        subscores: list[SubScore] = []
        for sub in family["subcriteria"]:
            method = METHODS.get(sub["method"])
            if method is None:
                subscores.append(
                    _zero(sub, family["key"], "méthode de notation inconnue dans la grille.")
                )
                continue
            try:
                result = method(sub, family["key"], facts)
            except Exception as exc:  # noqa: BLE001 - un échec vaut zéro documenté, jamais une invention
                result = _zero(
                    sub,
                    family["key"],
                    f"le calcul n'a pas abouti sur les données disponibles ({type(exc).__name__}).",
                )
            # Le plafond du sous-critère est réappliqué quoi qu'il arrive.
            result.score = max(0, min(result.score, sub["max"]))
            subscores.append(result)

        computed = sum(item.score for item in subscores)
        declared_max = sum(item.max for item in subscores)
        if declared_max != family["max"]:
            raise ValueError(
                f"Grille incohérente : la famille {family['key']} totalise {declared_max} "
                f"points de sous-critères pour un plafond déclaré de {family['max']}."
            )
        families.append(
            FamilyScore(
                key=family["key"],
                label=family["label"],
                score=min(computed, family["max"]),
                max=family["max"],
                subscores=subscores,
            )
        )

    total = sum(item.score for item in families)
    maximum = sum(item.max for item in families)
    if maximum != grid["total"]:
        raise ValueError(
            f"Grille incohérente : {maximum} points de familles pour un total déclaré de "
            f"{grid['total']}."
        )

    return ScientificScore(
        total=total,
        maximum=maximum,
        grid_version=grid["grid_version"],
        families=families,
        notice=grid["notice"],
    )


def to_dict(result: ScientificScore) -> dict:
    return {
        "total": result.total,
        "maximum": result.maximum,
        "grid_version": result.grid_version,
        "notice": result.notice,
        "families": [
            {
                "key": family.key,
                "label": family.label,
                "score": family.score,
                "max": family.max,
                "subscores": [
                    {
                        "key": sub.key,
                        "label": sub.label,
                        "score": sub.score,
                        "max": sub.max,
                        "justification": sub.justification,
                        "evidence_ids": sub.evidence_ids,
                        "method": sub.method,
                    }
                    for sub in family.subscores
                ],
            }
            for family in result.families
        ],
        "undocumented": [sub.key for sub in result.subscores if not sub.documented],
    }
