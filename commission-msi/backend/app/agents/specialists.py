"""Les six agents spécialisés du module de recherche contrôlée."""

from __future__ import annotations

from app.agents.base import (
    MIN_INDEPENDENT_SOURCES,
    Agent,
    AgentInput,
    AgentOutput,
    AxisProposal,
    Claim,
    affiliation_agreement,
    confidence_of,
    evidence_status,
    independent_domains,
    label_matches,
    mentions,
    no_result_claim,
)
from app.core.vocabulary import AgentName, ClaimNature, EvidenceStatus, SourceTier

#: Taux de contenance au-delà duquel l'affiliation déclarée est jugée retrouvée.
SAME_IDENTITY_THRESHOLD = 0.86
#: Taux minimal pour considérer qu'une source parle bien du sujet recherché.
HOMONYM_THRESHOLD = 0.60

#: Signaux publics de revue ou de conférence prédatrice.
PREDATORY_SIGNALS = (
    "guaranteed publication",
    "publication garantie",
    "predatory",
    "prédatrice",
    "pay to publish",
    "fast track publication",
    "acceptance within 48",
)


class IdentityAffiliationsAgent(Agent):
    """Désambiguïsation des personnes, institutions et variantes de noms."""

    name = AgentName.IDENTITE_AFFILIATIONS

    #: La désambiguïsation d'identité ne concerne pas l'intitulé d'un événement :
    #: un même colloque apparaît normalement sur plusieurs sites.
    IDENTITY_SUBJECTS = frozenset({"PERSONNE", "INSTITUTION", "PARTENAIRE", "SPONSOR", "FINANCEUR"})

    def run(self, data: AgentInput) -> AgentOutput:
        output = self._output(data)
        if not data.results:
            output.claims.append(no_result_claim(self.name, data.subject_label))
            return output

        if data.subject_kind not in self.IDENTITY_SUBJECTS:
            matched = [
                result
                for result in data.results
                if label_matches(data.subject_label, result) >= HOMONYM_THRESHOLD
            ]
            output.claims.append(
                Claim(
                    agent_name=self.name,
                    subject_label=data.subject_label,
                    statement=(
                        f"{len(matched)} source(s) publique(s) mentionnent « {data.subject_label} ». "
                        "Aucune désambiguïsation d'identité n'est requise pour un intitulé de manifestation."
                    ),
                    nature=ClaimNature.FAIT_VERIFIE if matched else ClaimNature.ABSENCE_DE_PREUVE,
                    status=evidence_status(matched),
                    confidence=confidence_of(matched),
                    source_urls=[result.url for result in matched],
                    independent_source_count=len(independent_domains(matched)),
                    notes="La présence d'un intitulé sur plusieurs sites ne prouve pas sa légitimité.",
                )
            )
            return output

        agreement = affiliation_agreement(data.declared_affiliation, data.results)
        candidates = [
            result for result in data.results if label_matches(data.subject_label, result) >= HOMONYM_THRESHOLD
        ]
        distinct = independent_domains(candidates)

        if data.declared_affiliation and agreement >= SAME_IDENTITY_THRESHOLD:
            status = evidence_status(candidates)
            statement = (
                f"L'affiliation déclarée « {data.declared_affiliation } » est cohérente avec "
                f"les sources publiques trouvées pour « {data.subject_label} » "
                f"(similarité {agreement:.2f})."
            )
            nature = ClaimNature.FAIT_VERIFIE if status in {
                EvidenceStatus.SOURCE_OFFICIELLE_TROUVEE,
                EvidenceStatus.SOURCES_CONCORDANTES,
            } else ClaimNature.ALLEGATION_TIERS
        elif len(distinct) > 1 and agreement < SAME_IDENTITY_THRESHOLD:
            status = EvidenceStatus.HOMONYMIE_POSSIBLE
            statement = (
                f"Plusieurs profils publics distincts portent un nom proche de "
                f"« {data.subject_label} » ({len(distinct)} domaines indépendants). "
                "L'identification n'est pas établie."
            )
            nature = ClaimNature.ABSENCE_DE_PREUVE
        else:
            status = EvidenceStatus.A_VERIFIER
            statement = (
                f"Des sources publiques mentionnent « {data.subject_label} », mais "
                "l'affiliation déclarée n'a pas pu être confirmée."
            )
            nature = ClaimNature.ALLEGATION_TIERS

        output.claims.append(
            Claim(
                agent_name=self.name,
                subject_label=data.subject_label,
                statement=statement,
                nature=nature,
                status=status,
                confidence=confidence_of(candidates or data.results),
                source_urls=[result.url for result in (candidates or data.results)],
                independent_source_count=len(distinct),
                notes=(
                    "Une homonymie possible interdit toute conclusion consolidée sur cette personne."
                    if status == EvidenceStatus.HOMONYMIE_POSSIBLE
                    else "La désambiguïsation reste soumise au contrôle humain."
                ),
            )
        )
        return output


class PublicIntegrityAgent(Agent):
    """Engagements associatifs, fonctions publiques et conflits d'intérêts publics."""

    name = AgentName.INTEGRITE_PUBLIQUE

    ROLE_TERMS = (
        "association",
        "president",
        "président",
        "board",
        "conseil d'administration",
        "editorial board",
        "comité éditorial",
        "fondation",
        "foundation",
        "ONG",
        "NGO",
    )

    def run(self, data: AgentInput) -> AgentOutput:
        output = self._output(data)
        if not data.results:
            output.claims.append(no_result_claim(self.name, data.subject_label))
            return output

        found_any = False
        for term in self.ROLE_TERMS:
            matched = mentions(term, data.results)
            if not matched:
                continue
            found_any = True
            domains = independent_domains(matched)
            status = evidence_status(matched)
            if status == EvidenceStatus.A_VERIFIER and len(domains) < MIN_INDEPENDENT_SOURCES:
                nature = ClaimNature.ALLEGATION_TIERS
            else:
                nature = ClaimNature.FAIT_VERIFIE
            output.claims.append(
                Claim(
                    agent_name=self.name,
                    subject_label=data.subject_label,
                    statement=(
                        f"Une activité publique de type « {term} » est mentionnée en lien avec "
                        f"« {data.subject_label} » dans {len(domains)} source(s) indépendante(s)."
                    ),
                    nature=nature,
                    status=status,
                    confidence=confidence_of(matched),
                    source_urls=[result.url for result in matched],
                    independent_source_count=len(domains),
                    notes=(
                        "Une appartenance, une présence à un événement, une signature collective "
                        "ou un abonnement ne prouvent pas l'adhésion à toutes les positions de "
                        "l'organisation, et ne constituent pas une incompatibilité."
                    ),
                )
            )
        if not found_any:
            output.claims.append(no_result_claim(self.name, data.subject_label))
        return output


class AlgerianLawAgent(Agent):
    """Rapprochement avec le seul référentiel algérien officiel validé.

    Sans texte officiel présent, validé et daté dans le référentiel local,
    l'agent ne produit aucun rapprochement : il signale l'absence de base.
    """

    name = AgentName.DROIT_ALGERIEN

    def run(self, data: AgentInput) -> AgentOutput:
        output = self._output(data)
        usable = [
            reference
            for reference in data.algerian_references
            if reference.get("status") == "VALIDE"
            and reference.get("integrity_ok")
            and reference.get("passages")
        ]
        if not usable:
            output.claims.append(
                Claim(
                    agent_name=self.name,
                    subject_label=data.subject_label,
                    statement=(
                        "Aucun rapprochement juridique n'est possible : le référentiel algérien "
                        "local ne contient aucun texte officiel validé, d'empreinte cohérente et "
                        "rattaché à un passage paginé."
                    ),
                    nature=ClaimNature.ABSENCE_DE_PREUVE,
                    status=EvidenceStatus.NON_ETABLI,
                    confidence=None,
                    notes=(
                        "La notion de « principes de l'Algérie » n'est jamais interprétée librement. "
                        "Toute qualification juridique est réservée aux autorités compétentes."
                    ),
                )
            )
            return output

        for reference in usable:
            output.claims.append(
                Claim(
                    agent_name=self.name,
                    subject_label=data.subject_label,
                    statement=(
                        f"Point à examiner au regard de « {reference['title']} » "
                        f"({reference.get('reference') or 'référence non précisée'}, "
                        f"{reference.get('document_date') or 'date non précisée'}), "
                        f"passage p. {reference['passages'][0].get('page_no')}."
                    ),
                    nature=ClaimNature.OPINION,
                    status=EvidenceStatus.A_VERIFIER,
                    confidence=None,
                    notes=(
                        "Rapprochement documentaire uniquement. L'agent ne qualifie ni infraction, "
                        "ni incompatibilité : cette qualification revient à l'évaluateur et aux "
                        "autorités compétentes."
                    ),
                )
            )
        return output


class ScientificReputationAgent(Agent):
    """Réputation académique, indexation, rétractations et signaux prédateurs."""

    name = AgentName.REPUTATION_SCIENTIFIQUE

    def run(self, data: AgentInput) -> AgentOutput:
        output = self._output(data)
        if not data.results:
            output.claims.append(no_result_claim(self.name, data.subject_label))
            output.axis_proposals.append(
                AxisProposal(
                    axis_key="comite_intervenants",
                    proposed_score=None,
                    uncertainty_low=None,
                    uncertainty_high=None,
                    evidence_sufficient=False,
                    rationale="Aucune source publique : axe non renseigné.",
                )
            )
            return output

        scientific = [
            result
            for result in data.results
            if result.tier
            in {SourceTier.T3_PUBLICATION_SCIENTIFIQUE, SourceTier.T2_INSTITUTION_ACADEMIQUE}
        ]
        domains = independent_domains(scientific)
        output.claims.append(
            Claim(
                agent_name=self.name,
                subject_label=data.subject_label,
                statement=(
                    f"{len(scientific)} source(s) scientifique(s) ou institutionnelle(s) "
                    f"réparties sur {len(domains)} domaine(s) mentionnent « {data.subject_label} »."
                ),
                nature=ClaimNature.FAIT_VERIFIE if scientific else ClaimNature.ABSENCE_DE_PREUVE,
                status=evidence_status(scientific),
                confidence=confidence_of(scientific),
                source_urls=[result.url for result in scientific],
                independent_source_count=len(domains),
                notes="Le volume de publications ne mesure ni la qualité ni l'intégrité.",
            )
        )

        for signal in PREDATORY_SIGNALS:
            matched = mentions(signal, data.results)
            if matched:
                output.claims.append(
                    Claim(
                        agent_name=self.name,
                        subject_label=data.subject_label,
                        statement=(
                            f"Signal public de pratique éditoriale douteuse : « {signal} » "
                            "apparaît dans une source consultée."
                        ),
                        nature=ClaimNature.ALLEGATION_TIERS,
                        status=EvidenceStatus.A_VERIFIER,
                        confidence=confidence_of(matched),
                        source_urls=[result.url for result in matched],
                        independent_source_count=len(independent_domains(matched)),
                        notes="Un signal isolé n'établit pas le caractère prédateur d'une revue.",
                    )
                )

        sufficient = len(domains) >= MIN_INDEPENDENT_SOURCES
        output.axis_proposals.append(
            AxisProposal(
                axis_key="comite_intervenants",
                proposed_score=round(min(20.0, 4.0 * len(domains)), 2) if sufficient else None,
                uncertainty_low=round(max(0.0, 4.0 * len(domains) - 4), 2) if sufficient else None,
                uncertainty_high=round(min(20.0, 4.0 * len(domains) + 4), 2) if sufficient else None,
                evidence_sufficient=sufficient,
                rationale=(
                    f"Traçabilité fondée sur {len(domains)} domaine(s) indépendant(s) de niveau "
                    "scientifique ou institutionnel."
                    if sufficient
                    else "Preuves insuffisantes : axe non renseigné."
                ),
                source_urls=[result.url for result in scientific],
            )
        )
        return output


class EventRankingAgent(Agent):
    """Évaluation comparative de la manifestation sur les axes du ranking externe."""

    name = AgentName.RANKING_MANIFESTATION

    AXIS_TERMS: dict[str, tuple[str, ...]] = {
        "reputation_historique": ("edition", "édition", "annual", "annuel", "since", "depuis"),
        "credibilite_organisateur": ("university", "université", "institute", "institut", "faculty"),
        "comite_intervenants": ("scientific committee", "comité scientifique", "keynote", "speaker"),
        "selectivite_programme": ("call for papers", "appel à communication", "peer review", "acceptance rate"),
        "publication_indexation": ("proceedings", "indexed", "scopus", "doi", "isbn", "issn"),
        "portee_internationale": ("international", "countries", "pays", "worldwide"),
        "transparence_partenaires": ("sponsor", "partner", "partenaire", "funding", "conflict of interest"),
    }
    AXIS_MAX: dict[str, int] = {
        "reputation_historique": 20,
        "credibilite_organisateur": 15,
        "comite_intervenants": 20,
        "selectivite_programme": 15,
        "publication_indexation": 15,
        "portee_internationale": 10,
        "transparence_partenaires": 5,
    }

    def run(self, data: AgentInput) -> AgentOutput:
        output = self._output(data)
        if not data.results:
            output.claims.append(no_result_claim(self.name, data.subject_label))
            for axis_key in self.AXIS_TERMS:
                output.axis_proposals.append(
                    AxisProposal(
                        axis_key=axis_key,
                        proposed_score=None,
                        uncertainty_low=None,
                        uncertainty_high=None,
                        evidence_sufficient=False,
                        rationale="Aucune source publique consultable : axe non renseigné.",
                    )
                )
            return output

        for axis_key, terms in self.AXIS_TERMS.items():
            matched: list = []
            for term in terms:
                matched.extend(mentions(term, data.results))
            unique = {result.url: result for result in matched}.values()
            domains = independent_domains(list(unique))
            maximum = self.AXIS_MAX[axis_key]
            sufficient = len(domains) >= MIN_INDEPENDENT_SOURCES
            score = round(min(float(maximum), maximum * len(domains) / 4), 2) if sufficient else None
            output.axis_proposals.append(
                AxisProposal(
                    axis_key=axis_key,
                    proposed_score=score,
                    uncertainty_low=round(max(0.0, score - maximum * 0.2), 2) if score else None,
                    uncertainty_high=round(min(float(maximum), score + maximum * 0.2), 2) if score else None,
                    evidence_sufficient=sufficient,
                    rationale=(
                        f"{len(domains)} domaine(s) indépendant(s) documentent cet axe."
                        if sufficient
                        else "Preuves insuffisantes : axe non renseigné (NR)."
                    ),
                    source_urls=[result.url for result in unique],
                )
            )
        return output


class SourceVerifierAgent(Agent):
    """Contrôle des citations, dates, homonymies, contradictions et niveau de preuve."""

    name = AgentName.VERIFICATEUR_SOURCES

    def run(self, data: AgentInput) -> AgentOutput:
        output = self._output(data)
        if not data.results:
            output.claims.append(no_result_claim(self.name, data.subject_label))
            return output

        undated = [result for result in data.results if not result.published_on]
        if undated:
            output.claims.append(
                Claim(
                    agent_name=self.name,
                    subject_label=data.subject_label,
                    statement=f"{len(undated)} source(s) consultée(s) ne portent aucune date de publication.",
                    nature=ClaimNature.ABSENCE_DE_PREUVE,
                    status=EvidenceStatus.A_VERIFIER,
                    confidence=None,
                    source_urls=[result.url for result in undated],
                    notes="Une source non datée ne peut pas confirmer un point sensible.",
                )
            )

        weak = [
            result
            for result in data.results
            if result.tier in {SourceTier.T6_RESEAU_SOCIAL_OFFICIEL, SourceTier.T7_NON_ATTRIBUE}
        ]
        if weak:
            output.claims.append(
                Claim(
                    agent_name=self.name,
                    subject_label=data.subject_label,
                    statement=(
                        f"{len(weak)} source(s) de faible niveau de preuve (réseau social ou "
                        "contenu non attribué) figurent dans les résultats."
                    ),
                    nature=ClaimNature.RUMEUR,
                    status=EvidenceStatus.NON_ETABLI,
                    confidence=None,
                    source_urls=[result.url for result in weak],
                    notes=(
                        "Agrégateurs anonymes, captures sans origine, forums et publications non "
                        "attribuées ne peuvent jamais suffire à confirmer un point sensible."
                    ),
                )
            )

        official = [result for result in data.results if result.tier == SourceTier.T1_AUTORITE_OFFICIELLE]
        secondary = [result for result in data.results if result.tier == SourceTier.T5_MEDIA_RECONNU]
        if official and secondary:
            output.claims.append(
                Claim(
                    agent_name=self.name,
                    subject_label=data.subject_label,
                    statement=(
                        "Une source officielle et une source médiatique coexistent sur ce sujet : "
                        "leur concordance doit être vérifiée manuellement."
                    ),
                    nature=ClaimNature.OPINION,
                    status=EvidenceStatus.SOURCES_CONTRADICTOIRES
                    if len(secondary) > len(official)
                    else EvidenceStatus.A_VERIFIER,
                    confidence=None,
                    source_urls=[result.url for result in official + secondary],
                    notes="En cas de divergence, la source officielle primaire prévaut.",
                )
            )
        return output


from app.agents.sovereignty import SovereigntyScreeningAgent

ALL_AGENTS: tuple[Agent, ...] = (
    IdentityAffiliationsAgent(),
    PublicIntegrityAgent(),
    SovereigntyScreeningAgent(),
    AlgerianLawAgent(),
    ScientificReputationAgent(),
    EventRankingAgent(),
    SourceVerifierAgent(),
)
