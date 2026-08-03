"""Vocabulaire contrôlé (donnees/statuts_et_decisions.json du kit).

Aucune valeur automatique interdite ne peut être produite par le moteur.
"""

from __future__ import annotations

from enum import StrEnum


class DossierStatus(StrEnum):
    NOUVEAU = "NOUVEAU"
    ANALYSE_EN_COURS = "ANALYSE_EN_COURS"
    RECHERCHE_WEB_REQUISE = "RECHERCHE_WEB_REQUISE"
    RECHERCHE_WEB_EN_COURS = "RECHERCHE_WEB_EN_COURS"
    A_CONTROLER = "A_CONTROLER"
    EN_EVALUATION = "EN_EVALUATION"
    COMPLEMENT_REQUIS = "COMPLEMENT_REQUIS"
    ANALYSE_ENRICHIE_COMPLETE = "ANALYSE_ENRICHIE_COMPLETE"
    PRET_POUR_RAPPORT = "PRET_POUR_RAPPORT"
    ARCHIVE = "ARCHIVE"


class JobState(StrEnum):
    """États du travail d'analyse durable (§6 du prompt maître V4)."""

    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    EXTRACTING = "EXTRACTING"
    OCR = "OCR"
    SEMANTIC_READING = "SEMANTIC_READING"
    STRUCTURING = "STRUCTURING"
    REGULATORY_CHECK = "REGULATORY_CHECK"
    SCIENTIFIC_SCORING = "SCIENTIFIC_SCORING"
    WEB_RESEARCH = "WEB_RESEARCH"
    INDEPENDENT_AUDIT = "INDEPENDENT_AUDIT"
    REPORT_BUILDING = "REPORT_BUILDING"
    REPORT_QA = "REPORT_QA"
    REPORT_RENDERING = "REPORT_RENDERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


#: États terminaux : le worker ne les reprend jamais.
TERMINAL_JOB_STATES = frozenset({JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED})

#: Libellés affichés à l'évaluateur pendant le traitement.
JOB_STATE_LABELS: dict[str, str] = {
    JobState.QUEUED: "En file d'attente",
    JobState.VALIDATING: "Validation du document source",
    JobState.EXTRACTING: "Extraction du texte page par page",
    JobState.OCR: "Reconnaissance optique des pages scannées",
    JobState.SEMANTIC_READING: "Lecture sémantique assistée du dossier",
    JobState.STRUCTURING: "Structuration des informations et registre de preuves",
    JobState.REGULATORY_CHECK: "Application des 26 critères réglementaires",
    JobState.SCIENTIFIC_SCORING: "Calcul du score scientifique sur 100",
    JobState.WEB_RESEARCH: "Vérification publique des intervenants étrangers",
    JobState.INDEPENDENT_AUDIT: "Relecture indépendante et règle de consensus",
    JobState.REPORT_BUILDING: "Rédaction du rapport",
    JobState.REPORT_QA: "Contrôle qualité du rapport",
    JobState.REPORT_RENDERING: "Production du rapport harmonisé (Word et PDF)",
    JobState.COMPLETED: "Terminé",
    JobState.FAILED: "Interrompu",
    JobState.CANCELLED: "Annulé",
}


class CriterionStatus(StrEnum):
    """Statut réglementaire d'un critère — jamais vide, jamais inventé."""

    C = "C"
    PC = "PC"
    NC = "NC"
    NV = "NV"


CRITERION_STATUS_LABELS: dict[str, str] = {
    CriterionStatus.C: "Conforme",
    CriterionStatus.PC: "Partiellement conforme",
    CriterionStatus.NC: "Non conforme",
    CriterionStatus.NV: "Non vérifiable",
}


class EvidenceKind(StrEnum):
    """Origine d'une preuve du registre."""

    DOCUMENT = "DOCUMENT"
    PAGE = "PAGE"
    PIECE = "PIECE"
    CALCUL = "CALCUL"
    SOURCE_WEB = "SOURCE_WEB"
    SAISIE_HUMAINE = "SAISIE_HUMAINE"


class InformationStatus(StrEnum):
    A_VERIFIER = "A_VERIFIER"
    CONFIRME = "CONFIRME"
    CORRIGE = "CORRIGE"
    REJETE = "REJETE"
    INCERTAIN = "INCERTAIN"
    NON_APPLICABLE = "NON_APPLICABLE"


class PieceStatus(StrEnum):
    ABSENTE = "ABSENTE"
    DETECTEE = "DETECTEE"
    CONFIRMEE = "CONFIRMEE"
    INCOMPLETE = "INCOMPLETE"
    ILLISIBLE = "ILLISIBLE"
    NON_CONFORME = "NON_CONFORME"
    A_VERIFIER = "A_VERIFIER"
    NON_APPLICABLE = "NON_APPLICABLE"


class ControlStatus(StrEnum):
    CONFIRME = "CONFIRME"
    NON_CONFIRME = "NON_CONFIRME"
    INCOMPLET = "INCOMPLET"
    INCOHERENT = "INCOHERENT"
    ILLISIBLE = "ILLISIBLE"
    A_VERIFIER = "A_VERIFIER"
    NON_APPLICABLE = "NON_APPLICABLE"


class FindingStatus(StrEnum):
    A_VERIFIER = "A_VERIFIER"
    CONFIRME = "CONFIRME"
    ECARTE = "ECARTE"
    INCERTAIN = "INCERTAIN"
    NON_APPLICABLE = "NON_APPLICABLE"
    TRANSMIS = "TRANSMIS"


#: Statuts d'alerte exigeant une motivation humaine explicite.
FINDING_STATUSES_REQUIRING_MOTIVATION = frozenset(
    {FindingStatus.CONFIRME, FindingStatus.ECARTE, FindingStatus.TRANSMIS}
)


class Priority(StrEnum):
    FAIBLE = "FAIBLE"
    MOYEN = "MOYEN"
    ELEVE = "ELEVE"
    CRITIQUE = "CRITIQUE"


class Conclusion(StrEnum):
    AVIS_FAVORABLE = "AVIS_FAVORABLE"
    AVIS_FAVORABLE_SOUS_RESERVES = "AVIS_FAVORABLE_SOUS_RESERVES"
    AJOURNEMENT_COMPLEMENT_INFORMATION = "AJOURNEMENT_COMPLEMENT_INFORMATION"
    NON_ELIGIBILITE_QUALIFICATION_INTERNATIONALE = "NON_ELIGIBILITE_QUALIFICATION_INTERNATIONALE"
    POSSIBILITE_REQUALIFICATION = "POSSIBILITE_REQUALIFICATION"
    TRANSMISSION_COMMISSION_AVEC_VIGILANCE = "TRANSMISSION_COMMISSION_AVEC_VIGILANCE"
    TRANSMISSION_TUTELLE_ALERTE_MOTIVEE = "TRANSMISSION_TUTELLE_ALERTE_MOTIVEE"
    NON_DETERMINABLE_INFORMATION_INSUFFISANTE = "NON_DETERMINABLE_INFORMATION_INSUFFISANTE"


#: Sorties que le système ne doit jamais produire automatiquement.
FORBIDDEN_AUTOMATIC_OUTPUTS = frozenset(
    {"ACCEPTE", "REJETE", "INTERDIT", "NOTE_AUTOMATIQUE", "AVIS_DEFINITIF"}
)


class ExtractionMode(StrEnum):
    NATIF = "NATIF"
    OCR = "OCR"
    MIXTE = "MIXTE"
    AUCUN = "AUCUN"
    SAISIE_MANUELLE = "SAISIE_MANUELLE"


class Sensitivity(StrEnum):
    ORDINAIRE = "ORDINAIRE"
    RESTREINT = "RESTREINT"


class RegulationStatus(StrEnum):
    BROUILLON = "BROUILLON"
    A_VERIFIER = "A_VERIFIER"
    VALIDE = "VALIDE"
    ABROGE = "ABROGE"
    SUSPENDU = "SUSPENDU"


class Gate(StrEnum):
    G0_SOURCE = "G0_SOURCE"
    G1_EXTRACTION = "G1_EXTRACTION"
    G2_ADMINISTRATIF = "G2_ADMINISTRATIF"
    G3_ELIGIBILITE = "G3_ELIGIBILITE"
    G4_SCIENTIFIQUE = "G4_SCIENTIFIQUE"
    G5_VIGILANCE = "G5_VIGILANCE"
    G6_RAPPORT = "G6_RAPPORT"
    G7_VALIDATION_HUMAINE = "G7_VALIDATION_HUMAINE"


class MarocRelation(StrEnum):
    MENTION_GEOGRAPHIQUE = "MENTION_GEOGRAPHIQUE"
    REFERENCE_BIBLIOGRAPHIQUE = "REFERENCE_BIBLIOGRAPHIQUE"
    AFFILIATION = "AFFILIATION"
    NATIONALITE_DECLAREE = "NATIONALITE_DECLAREE"
    INTERVENANT = "INTERVENANT"
    PARTICIPANT = "PARTICIPANT"
    PARTENAIRE = "PARTENAIRE"
    SPONSOR = "SPONSOR"
    FINANCEUR = "FINANCEUR"
    COMITE = "COMITE"
    ORGANISATEUR = "ORGANISATEUR"
    COOPERATION_ENVISAGEE = "COOPERATION_ENVISAGEE"
    AUTRE = "AUTRE"


class ReportFactKind(StrEnum):
    """Étiquetage visuel obligatoire des contenus du rapport."""

    FAIT_EXTRAIT = "FAIT_EXTRAIT"
    CALCUL = "CALCUL"
    ALERTE_SYSTEME = "ALERTE_SYSTEME"
    COMMENTAIRE_EVALUATEUR = "COMMENTAIRE_EVALUATEUR"
    CONCLUSION_EVALUATEUR = "CONCLUSION_EVALUATEUR"
    A_VERIFIER = "A_VERIFIER"


class EvidenceStatus(StrEnum):
    """Statut d'une affirmation issue de la recherche Web contrôlée."""

    A_VERIFIER = "A_VERIFIER"
    SOURCE_OFFICIELLE_TROUVEE = "SOURCE_OFFICIELLE_TROUVEE"
    SOURCES_CONCORDANTES = "SOURCES_CONCORDANTES"
    SOURCES_CONTRADICTOIRES = "SOURCES_CONTRADICTOIRES"
    HOMONYMIE_POSSIBLE = "HOMONYMIE_POSSIBLE"
    NON_ETABLI = "NON_ETABLI"
    ECARTE_PAR_HUMAIN = "ECARTE_PAR_HUMAIN"


class ClaimNature(StrEnum):
    """Nature d'une affirmation : jamais confondre fait et rumeur."""

    FAIT_VERIFIE = "FAIT_VERIFIE"
    DECLARATION_INTERESSE = "DECLARATION_INTERESSE"
    ALLEGATION_TIERS = "ALLEGATION_TIERS"
    OPINION = "OPINION"
    RUMEUR = "RUMEUR"
    ABSENCE_DE_PREUVE = "ABSENCE_DE_PREUVE"


class SourceTier(StrEnum):
    """Hiérarchie de qualité des sources publiques (section 9.3 du prompt V3)."""

    T1_AUTORITE_OFFICIELLE = "T1_AUTORITE_OFFICIELLE"
    T2_INSTITUTION_ACADEMIQUE = "T2_INSTITUTION_ACADEMIQUE"
    T3_PUBLICATION_SCIENTIFIQUE = "T3_PUBLICATION_SCIENTIFIQUE"
    T4_SITE_ORGANISATEUR = "T4_SITE_ORGANISATEUR"
    T5_MEDIA_RECONNU = "T5_MEDIA_RECONNU"
    T6_RESEAU_SOCIAL_OFFICIEL = "T6_RESEAU_SOCIAL_OFFICIEL"
    T7_NON_ATTRIBUE = "T7_NON_ATTRIBUE"


#: Niveaux de preuve associés à chaque palier de source.
SOURCE_TIER_WEIGHT: dict[str, float] = {
    SourceTier.T1_AUTORITE_OFFICIELLE: 1.0,
    SourceTier.T2_INSTITUTION_ACADEMIQUE: 0.85,
    SourceTier.T3_PUBLICATION_SCIENTIFIQUE: 0.8,
    SourceTier.T4_SITE_ORGANISATEUR: 0.6,
    SourceTier.T5_MEDIA_RECONNU: 0.5,
    SourceTier.T6_RESEAU_SOCIAL_OFFICIEL: 0.25,
    SourceTier.T7_NON_ATTRIBUE: 0.0,
}


class AgentName(StrEnum):
    IDENTITE_AFFILIATIONS = "AGENT_IDENTITE_AFFILIATIONS"
    INTEGRITE_PUBLIQUE = "AGENT_INTEGRITE_PUBLIQUE"
    SOUVERAINETE_NATIONALE = "AGENT_SOUVERAINETE_NATIONALE"
    DROIT_ALGERIEN = "AGENT_DROIT_ALGERIEN"
    REPUTATION_SCIENTIFIQUE = "AGENT_REPUTATION_SCIENTIFIQUE"
    RANKING_MANIFESTATION = "AGENT_RANKING_MANIFESTATION"
    VERIFICATEUR_SOURCES = "AGENT_VERIFICATEUR_SOURCES"


class WebRunStatus(StrEnum):
    PREPAREE = "PREPAREE"
    EN_COURS = "EN_COURS"
    EN_PAUSE = "EN_PAUSE"
    TERMINEE = "TERMINEE"
    ECHOUEE = "ECHOUEE"
    ANNULEE = "ANNULEE"
    ECARTEE_PAR_HUMAIN = "ECARTEE_PAR_HUMAIN"


class RankingGrade(StrEnum):
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    NR = "NR"


#: Message affiché lorsque la recherche Web est impossible.
WEB_UNAVAILABLE_MESSAGE = (
    "Recherche Web indisponible — analyse enrichie incomplète, vérification humaine "
    "externe obligatoire."
)
AGENT_DISAGREEMENT_MESSAGE = "DESACCORD_AGENTS — ARBITRAGE_HUMAIN_OBLIGATOIRE"
RANKING_TITLE = (
    "Classement externe indicatif assisté par IA — non décisionnel, fondé sur des "
    "sources publiques consultées à la date indiquée."
)
NOT_PROVIDED = "NR — NON RENSEIGNE"


#: Limites que l'application doit afficher (section 27 du prompt maître V3).
DISPLAYED_LIMITS: tuple[str, ...] = (
    "Aucune garantie d'exhaustivité ni de zéro erreur.",
    "L'OCR est particulièrement fragile pour les noms propres, dates, montants et l'arabe.",
    "L'absence d'alerte ne prouve pas l'absence de risque.",
    "La détection textuelle ne suffit pas pour les drapeaux, cartes, logos, tampons et signatures.",
    "Les règles officielles sont susceptibles d'évoluer.",
    "La qualification juridique et diplomatique est réservée aux autorités compétentes.",
    "L'appréciation scientifique est réservée à l'évaluateur.",
    "Les résultats Web dépendent de la disponibilité, de l'indexation, de la langue et de la date de consultation.",
    "L'absence de résultat Web ne prouve ni l'absence d'activité ni l'absence de risque.",
    "Risque d'homonymie, de contenu obsolète, de désinformation et de biais des moteurs ou des agents.",
    "Le ranking IA est indicatif, non homologué et ne remplace ni l'évaluation réglementaire ni l'appréciation scientifique humaine.",
    "Qualifier une activité comme contraire à la loi relève des autorités compétentes, sur le seul fondement d'un texte algérien officiel validé.",
    "Prototype local, non équivalent à une plateforme institutionnelle homologuée.",
    "Le chiffrement applicatif ne remplace pas le chiffrement complet du disque.",
)
