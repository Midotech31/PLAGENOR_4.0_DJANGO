"""Chargement des données de référence versionnées du kit.

Aucune règle, pièce ou exigence n'est codée en dur dans le code applicatif :
tout provient de fichiers JSON versionnés et traçables.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import PROJECT_DIR

REFERENCES_DIR = PROJECT_DIR / "references_officielles"
DONNEES_DIR = REFERENCES_DIR / "donnees"
ORIGINALS_DIR = REFERENCES_DIR / "originaux"
RULES_FILE = PROJECT_DIR / "rules" / "default_rules.json"
COMPLEMENTARY_PIECES_FILE = PROJECT_DIR / "rules" / "pieces_complementaires.json"

#: Liste de contrôle administratif (section 9 du prompt maître).
ADMINISTRATIVE_CHECKLIST: tuple[tuple[str, str], ...] = (
    ("pieces_obligatoires", "Pièces obligatoires présentes et lisibles"),
    ("signatures_tampons", "Signatures et tampons"),
    ("visas_autorisations", "Visas et autorisations"),
    ("coherence_dates", "Cohérence des dates"),
    ("coherence_noms", "Cohérence des noms et variantes orthographiques"),
    ("affiliations", "Affiliations déclarées"),
    ("programme_vs_fiche", "Programme versus fiche technique"),
    ("programme_vs_theme", "Programme versus thème et objectifs"),
    ("budget_totaux_devise", "Budget, sous-totaux, total et devise"),
    ("partenaires_vs_justificatifs", "Partenaires versus justificatifs"),
    ("sponsors_vs_justificatifs", "Sponsors versus justificatifs"),
    ("intervenants_vs_affiliations", "Intervenants versus affiliations"),
    ("pays_annonces_vs_liste", "Nombre de pays annoncé versus liste réelle"),
    ("format_vs_programme", "Format annoncé versus programme"),
    ("publication_valorisation_suivi", "Publication, valorisation, livrables et suivi"),
    ("expiration_documents", "Expiration éventuelle de documents"),
    ("references_reglementaires", "Références réglementaires identifiables"),
)

#: Informations structurées attendues (section 8 du prompt maître).
#: (clé, libellé, contrôle renforcé)
INFORMATION_FIELDS: tuple[tuple[str, str, bool], ...] = (
    ("intitule", "Intitulé", True),
    ("type_manifestation", "Type de manifestation", False),
    ("theme", "Thème", False),
    ("objectifs", "Objectifs", False),
    ("date_debut", "Date de début", True),
    ("date_fin", "Date de fin", True),
    ("lieu", "Lieu", True),
    ("format", "Format (présentiel, hybride, à distance)", False),
    ("etablissement_organisateur", "Établissement organisateur", True),
    ("structure_porteuse", "Structure porteuse", True),
    ("responsable_scientifique", "Responsable scientifique", True),
    ("comite_scientifique", "Comité scientifique", True),
    ("comite_organisation", "Comité d'organisation", True),
    ("intervenants", "Intervenants", True),
    ("participants", "Participants", True),
    ("pays_representes", "Pays représentés", True),
    ("institutions_representees", "Institutions représentées", True),
    ("partenaires", "Partenaires", True),
    ("sponsors", "Sponsors", True),
    ("financeurs", "Financeurs", True),
    ("montants_devise", "Montants et devise", True),
    ("budget_total", "Budget total", True),
    ("modalites_publication", "Modalités de publication", False),
    ("livrables", "Livrables", False),
    ("resultats_attendus", "Résultats attendus", False),
    ("retombees_scientifiques", "Retombées scientifiques", False),
    ("retombees_doctorales", "Retombées doctorales", False),
    ("retombees_socio_economiques", "Retombées socio-économiques", False),
    ("references_reglementaires", "Références réglementaires citées", True),
)


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Donnée de référence absente : {path.name}. Le référentiel ne peut pas être chargé."
        )
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_pieces_catalogue() -> dict[str, Any]:
    return _load(DONNEES_DIR / "catalogue_pieces.json")


@lru_cache(maxsize=1)
def load_complementary_pieces() -> dict[str, Any]:
    """Pièces de travail complémentaires, non issues d'un canevas officiel."""
    return _load(COMPLEMENTARY_PIECES_FILE)


@lru_cache(maxsize=1)
def load_grid() -> dict[str, Any]:
    return _load(DONNEES_DIR / "grille_scientifique.json")


@lru_cache(maxsize=1)
def load_requirements() -> dict[str, Any]:
    return _load(DONNEES_DIR / "exigences_sourcees.json")


@lru_cache(maxsize=1)
def load_sources_manifest() -> dict[str, Any]:
    return _load(DONNEES_DIR / "manifest_sources.json")


@lru_cache(maxsize=1)
def load_missing_sources() -> dict[str, Any]:
    return _load(DONNEES_DIR / "sources_manquantes_a_valider.json")


@lru_cache(maxsize=1)
def load_acceptance_tests() -> dict[str, Any]:
    return _load(DONNEES_DIR / "tests_acceptation.json")


@lru_cache(maxsize=1)
def load_default_rules() -> dict[str, Any]:
    return _load(RULES_FILE)


def clear_cache() -> None:
    for loader in (
        load_pieces_catalogue,
        load_complementary_pieces,
        load_grid,
        load_requirements,
        load_sources_manifest,
        load_missing_sources,
        load_acceptance_tests,
        load_default_rules,
    ):
        loader.cache_clear()
