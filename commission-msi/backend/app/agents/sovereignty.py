"""Contrôle de souveraineté sur les profils publics des intervenants étrangers.

Ce que cet agent fait, et pourquoi il est légitime : la commission doit pouvoir
signaler au ministère un **rattachement institutionnel documenté** ou une
**activité publiquement établie** qui touche une catégorie de vigilance
nationale. Le modèle de rapport de la commission le fait explicitement — sa
section 4.1 cite des rattachements institutionnels avec leurs sources.

Ce que cet agent ne fait pas, et ne fera pas :

* **il ne profile personne par son origine.** Ni nationalité, ni origine
  ethnique, ni religion, ni lieu de naissance, ni consonance d'un nom ne sont
  des critères. Cette interdiction n'est pas une prudence ajoutée : elle est
  écrite dans le référentiel de l'application (« aucune déduction à partir de
  la nationalité, de l'origine ou d'une opinion supposée ») et dans l'encadré
  de portée du modèle de rapport de la commission ;
* **il ne conclut pas.** Il rapporte un fait public, sa source et sa date. La
  qualification — si tant est qu'il y en ait une — appartient au ministère ;
* **il n'invente pas de risque.** Sans source publique identifiable, il produit
  « non établi », jamais un soupçon.

Ce qui est donc examiné : le rattachement institutionnel déclaré ou publié, la
participation à des programmes ou consortiums nommés, et les fonctions
publiques exercées. Tout cela est de l'information professionnelle publique,
que la personne elle-même ou son institution a rendue publique.
"""

from __future__ import annotations

from app.agents.base import (
    Agent,
    AgentInput,
    AgentOutput,
    Claim,
    confidence_of,
    independent_domains,
    mentions,
    no_result_claim,
)
from app.core.vocabulary import AgentName, ClaimNature, EvidenceStatus

#: Nombre de sources indépendantes en deçà duquel un élément reste une
#: allégation, jamais un fait.
MIN_INDEPENDENT_SOURCES = 2

#: Mention obligatoire portée par chaque constat de cet agent.
INFORMATIVE_ONLY = (
    "Élément signalé à titre strictement informatif. Un rattachement "
    "institutionnel, une collaboration scientifique, une publication ou une "
    "participation à un programme ne constituent pas une non-conformité et ne "
    "préjugent d'aucune position personnelle. L'appréciation de leur pertinence "
    "et la décision relèvent exclusivement du ministère."
)

#: Ce que l'agent refuse d'examiner, énoncé pour être vérifiable.
NEVER_SCREENED = (
    "nationalité",
    "origine ethnique",
    "religion",
    "lieu de naissance",
    "consonance du nom",
    "opinion supposée",
)


class SovereigntyScreeningAgent(Agent):
    """Rattachements et activités publics touchant une catégorie de vigilance.

    L'agent ne porte aucun vocabulaire propre : il réutilise les termes du
    référentiel de vigilance déjà validé, de sorte qu'un ajout ou un retrait
    dans ce référentiel se répercute ici sans modification de code.
    """

    name = AgentName.SOUVERAINETE_NATIONALE

    #: Catégories du référentiel de vigilance examinées sur un profil public.
    #: Les catégories purement documentaires (format, calendrier) n'ont aucun
    #: sens appliquées à une personne et sont exclues.
    SCREENED_CATEGORIES = (
        "MENTIONS_MAROC",
        "INTEGRITE_TERRITORIALE",
        "RELATIONS_DIPLOMATIQUES",
        "DEFENSE_SECURITE",
        "INFRASTRUCTURES_CRITIQUES",
        "CYBER_DUAL_USE",
        "BIOSECURITE_DUAL_USE",
        "DONNEES_GENETIQUES_BIOMETRIQUES",
        "RESSOURCES_BIOLOGIQUES",
        "PATRIMOINE_ARCHIVES",
        "FINANCEMENT_INFLUENCE",
        "SOUVERAINETE_DONNEES",
    )

    #: Contextes où un terme sensible désigne un rattachement ou une activité,
    #: et non une simple mention géographique ou bibliographique.
    INSTITUTIONAL_CONTEXT = (
        "university",
        "université",
        "universite",
        "institute",
        "institut",
        "laboratory",
        "laboratoire",
        "research center",
        "centre de recherche",
        "consortium",
        "programme",
        "program",
        "project",
        "projet",
        "affiliation",
        "affiliated",
        "funded by",
        "financé par",
        "grant",
        "partnership",
        "partenariat",
    )

    #: Sujets sur lesquels ce contrôle a un sens. Une manifestation n'a ni
    #: rattachement ni activité propres : l'y appliquer produirait du bruit.
    SCREENED_SUBJECTS = ("PERSONNE", "INSTITUTION", "PARTENAIRE", "SPONSOR", "FINANCEUR")

    def run(self, data: AgentInput) -> AgentOutput:
        output = self._output(data)
        if data.subject_kind not in self.SCREENED_SUBJECTS:
            return output
        if not data.results:
            output.claims.append(no_result_claim(self.name, data.subject_label))
            return output

        found_any = False
        for category, terms in _screened_terms().items():
            for term in terms:
                matched = mentions(term, data.results)
                if not matched:
                    continue

                # Une mention isolée ne suffit pas : on exige un contexte
                # institutionnel, sans quoi une citation bibliographique ou une
                # simple mention géographique deviendrait un signalement.
                contextual = [
                    result
                    for result in matched
                    if any(
                        marker in f"{result.title or ''} {result.snippet or ''}".lower()
                        for marker in self.INSTITUTIONAL_CONTEXT
                    )
                ]
                if not contextual:
                    continue

                found_any = True
                domains = independent_domains(contextual)
                corroborated = len(domains) >= MIN_INDEPENDENT_SOURCES
                output.claims.append(
                    Claim(
                        agent_name=self.name,
                        subject_label=data.subject_label,
                        statement=(
                            f"Un rattachement ou une activité en lien avec « {term} » est "
                            f"documenté publiquement pour « {data.subject_label} », dans un "
                            f"contexte institutionnel, sur {len(domains)} source(s) "
                            f"indépendante(s). Catégorie de vigilance concernée : {category}."
                        ),
                        nature=(
                            ClaimNature.FAIT_VERIFIE
                            if corroborated
                            else ClaimNature.ALLEGATION_TIERS
                        ),
                        status=(
                            EvidenceStatus.SOURCES_CONCORDANTES
                            if corroborated
                            else EvidenceStatus.A_VERIFIER
                        ),
                        confidence=confidence_of(contextual),
                        source_urls=[result.url for result in contextual],
                        independent_source_count=len(domains),
                        notes=INFORMATIVE_ONLY,
                    )
                )

        if not found_any:
            output.claims.append(
                Claim(
                    agent_name=self.name,
                    subject_label=data.subject_label,
                    statement=(
                        f"Aucun rattachement institutionnel ni activité publique touchant une "
                        f"catégorie de vigilance n'a été établi pour « {data.subject_label} » "
                        "sur les sources consultées."
                    ),
                    nature=ClaimNature.ABSENCE_DE_PREUVE,
                    status=EvidenceStatus.NON_ETABLI,
                    confidence=None,
                    source_urls=[result.url for result in data.results],
                    independent_source_count=len(independent_domains(data.results)),
                    notes=(
                        "L'absence d'élément trouvé ne constitue ni une garantie, ni une "
                        "habilitation de sécurité : elle dépend de l'indexation, de la langue "
                        "et de la date de consultation."
                    ),
                )
            )
        return output


def _screened_terms() -> dict[str, tuple[str, ...]]:
    """Termes du référentiel de vigilance, restreints aux catégories examinées.

    Aucun vocabulaire n'est écrit ici : tout vient du référentiel validé, ce qui
    évite qu'une liste parallèle diverge silencieusement de celle qui fait foi.
    """
    from app.services import reference_data

    payload = reference_data.load_default_rules()
    rules = payload.get("rules", payload) if isinstance(payload, dict) else payload

    screened: dict[str, tuple[str, ...]] = {}
    for rule in rules:
        category = rule.get("category")
        if category not in SovereigntyScreeningAgent.SCREENED_CATEGORIES:
            continue
        terms = tuple(rule.get("terms") or ())
        if terms:
            screened[category] = screened.get(category, ()) + terms
    return screened


def screening_scope() -> dict:
    """Portée du contrôle, affichable et vérifiable par l'évaluateur."""
    terms = _screened_terms()
    return {
        "categories_examinees": list(terms),
        "termes_par_categorie": {name: len(values) for name, values in terms.items()},
        "jamais_examine": list(NEVER_SCREENED),
        "exigence_de_contexte": (
            "Un terme n'est retenu que s'il apparaît dans un contexte institutionnel "
            "— affiliation, programme, financement, partenariat. Une citation "
            "bibliographique ou une mention géographique ne déclenche rien."
        ),
        "portee": INFORMATIVE_ONLY,
    }
