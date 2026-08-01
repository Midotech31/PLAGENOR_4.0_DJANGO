"""Extraction automatique et contrôles calculés.

L'application propose ; l'évaluateur confirme. Ces tests vérifient que rien
n'est confirmé automatiquement et qu'aucune valeur n'est inventée.
"""

from __future__ import annotations

from app.core.vocabulary import ControlStatus, InformationStatus
from app.services.extraction_service import analyze_text, best_per_field
from tests.fixtures import synthetic

DOSSIER_COMPLET = """DEMANDE D'ORGANISATION D'UNE MANIFESTATION SCIENTIFIQUE INTERNATIONALE

Intitulé : Colloque international fictif sur les materiaux durables
Type de manifestation : colloque international
Thème : materiaux avances et transition energetique
Objectifs : structurer un reseau de recherche et former les doctorants
Dates : du 12 mars 2027 au 14 mars 2027
Lieu : Campus fictif, Alger
Format : hybride
Établissement organisateur : Universite Fictive de Test
Structure porteuse : Laboratoire fictif des materiaux
Responsable scientifique : Pr Amina Belkacem
Comité scientifique : Pr Jean Dubois, Pr Karim Idrissi
Comité d'organisation : Dr Sofiane Merabet
Conférenciers : Pr Zool Ismail, Pr Frederic Lasserre
Pays représentés : Algerie, France, Maroc
Partenaires : Institut Fictif de Lyon
Sponsors : Societe fictive d'ingenierie
Financement : subvention de l'etablissement
Budget total : 1 000 000 DA
Poste logistique : 700 000 DA
Poste communication : 400 000 DA
Modalités de publication : actes indexes et numero special de revue
Références réglementaires : Envoi n° 595/SG du 19 mai 2025
"""

PAGE_PROGRAMME = """Programme scientifique
Le programme se deroule du 20 juillet 2027 au 22 juillet 2027.
La manifestation reunit 12 pays.
"""


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------


def test_extraction_fills_the_main_fields_with_sources():
    report = analyze_text({1: DOSSIER_COMPLET})
    best = best_per_field(report)

    for key in (
        "intitule",
        "type_manifestation",
        "theme",
        "objectifs",
        "date_debut",
        "date_fin",
        "lieu",
        "format",
        "etablissement_organisateur",
        "structure_porteuse",
        "responsable_scientifique",
        "comite_scientifique",
        "comite_organisation",
        "intervenants",
        "pays_representes",
        "partenaires",
        "sponsors",
        "financeurs",
        "budget_total",
        "montants_devise",
        "modalites_publication",
        "references_reglementaires",
    ):
        assert key in best, f"champ non extrait : {key}"
        extraction = best[key]
        assert extraction.page_no == 1
        assert extraction.excerpt, f"extrait source manquant pour {key}"
        assert extraction.method, f"méthode de détection manquante pour {key}"
        assert 0 < extraction.confidence <= 1

    assert best["date_debut"].value == "12/03/2027"
    assert best["date_fin"].value == "14/03/2027"
    assert best["format"].value == "hybride"


def test_absent_field_is_never_invented():
    """Un champ sans correspondance textuelle n'est pas proposé du tout."""
    report = analyze_text({1: "Document fictif sans aucune information structuree."})
    best = best_per_field(report)
    for key in ("budget_total", "date_fin", "comite_scientifique", "sponsors"):
        assert key not in best


def test_country_detection_uses_word_boundaries():
    """« Inde » ne doit pas correspondre à « indexés »."""
    report = analyze_text({1: "Modalites de publication : actes indexes dans une base."})
    assert "Inde" not in (report.observations.get("countries") or [])

    report = analyze_text({1: "Pays representes : Algerie, Inde, France."})
    assert "Inde" in report.observations["countries"]


def test_total_is_detected_only_on_its_own_line():
    """Un « total » en ligne précédente ne qualifie pas le montant suivant."""
    report = analyze_text({1: "Budget total : 1 000 000 DA\nPoste logistique : 700 000 DA\n"})
    amounts = report.observations["amounts"]
    assert [(item["value"], item["is_total"]) for item in amounts] == [
        (1000000, True),
        (700000, False),
    ]


def test_institutions_are_deduplicated():
    report = analyze_text(
        {1: "Etablissement : Universite Fictive de Test\nLieu : Universite Fictive de Test, Alger\n"}
    )
    assert len(report.observations["institutions"]) == 1


def test_invalid_dates_are_rejected():
    report = analyze_text({1: "Reference 45/99/2027 et date reelle 12/03/2027."})
    values = {entry["value"] for entry in report.observations["dates"]}
    assert values == {"12/03/2027"}


# --------------------------------------------------------------------------
# Persistance : proposé, jamais confirmé
# --------------------------------------------------------------------------


def _import(client, dossier, pages):
    return client.post(
        f"/api/v1/dossiers/{dossier['id']}/documents",
        files={"file": ("dossier.pdf", synthetic.make_pdf(pages), "application/pdf")},
    )


def test_import_proposes_values_without_confirming_them(client, dossier):
    assert _import(client, dossier, [DOSSIER_COMPLET]).status_code == 201

    items = client.get(f"/api/v1/dossiers/{dossier['id']}/informations").json()["items"]
    filled = [item for item in items if item["current_value"]]
    assert len(filled) >= 15, "l'extraction doit renseigner la majorité des champs"

    for item in filled:
        # Rien n'est confirmé : la décision appartient à l'évaluateur.
        assert item["status"] == InformationStatus.A_VERIFIER
        assert item["manual_entry_validated"] is False
        assert item["page_no"] is not None, f"{item['key']} sans page source"
        assert item["source_excerpt"], f"{item['key']} sans extrait source"
        assert "détection :" in item["source_excerpt"]


def test_human_qualified_field_is_never_overwritten(client, dossier):
    assert _import(client, dossier, [DOSSIER_COMPLET]).status_code == 201
    items = {item["key"]: item for item in client.get(
        f"/api/v1/dossiers/{dossier['id']}/informations"
    ).json()["items"]}

    response = client.post(
        f"/api/v1/dossiers/{dossier['id']}/informations/{items['lieu']['id']}",
        json={
            "value": "Valeur corrigee par l'evaluateur",
            "status": InformationStatus.CORRIGE,
            "reason": "Correction apres lecture de la page originale.",
            "page_no": 1,
            "source_excerpt": "Lieu : Campus fictif, Alger",
        },
    )
    assert response.status_code == 200

    # Une nouvelle analyse ne doit pas écraser la correction humaine.
    again = client.post(f"/api/v1/dossiers/{dossier['id']}/analyse-complete")
    assert again.status_code == 200
    after = {item["key"]: item for item in client.get(
        f"/api/v1/dossiers/{dossier['id']}/informations"
    ).json()["items"]}
    assert after["lieu"]["current_value"] == "Valeur corrigee par l'evaluateur"
    assert after["lieu"]["status"] == InformationStatus.CORRIGE


# --------------------------------------------------------------------------
# Contrôles calculés
# --------------------------------------------------------------------------


def test_budget_incoherence_is_computed_and_explained(client, dossier):
    assert _import(client, dossier, [DOSSIER_COMPLET]).status_code == 201
    checks = {
        check["check_key"]: check
        for check in client.get(
            f"/api/v1/dossiers/{dossier['id']}/controle-administratif"
        ).json()["items"]
    }
    budget = checks["budget_totaux_devise"]
    assert budget["status"] == ControlStatus.INCOHERENT
    # Les deux valeurs comparées et l'écart sont affichés : le constat est refaisable.
    assert "1000000 DA" in budget["explanation"]
    assert "1100000 DA" in budget["explanation"]
    assert "Écart" in budget["explanation"]
    assert budget["comparison"]["total_declare"] == "1000000 DA"
    assert budget["comparison"]["somme_calculee"] == "1100000 DA"


def test_date_divergence_is_reported_with_both_pages(client, dossier):
    assert _import(client, dossier, [DOSSIER_COMPLET, PAGE_PROGRAMME]).status_code == 201
    checks = {
        check["check_key"]: check
        for check in client.get(
            f"/api/v1/dossiers/{dossier['id']}/controle-administratif"
        ).json()["items"]
    }
    dates = checks["coherence_dates"]
    assert dates["status"] == ControlStatus.INCOHERENT
    assert "page 1" in dates["explanation"] and "page 2" in dates["explanation"]
    assert dates["comparison"]["ecart_jours"] > 30


def test_country_count_mismatch_is_reported(client, dossier):
    assert _import(client, dossier, [DOSSIER_COMPLET, PAGE_PROGRAMME]).status_code == 201
    checks = {
        check["check_key"]: check
        for check in client.get(
            f"/api/v1/dossiers/{dossier['id']}/controle-administratif"
        ).json()["items"]
    }
    pays = checks["pays_annonces_vs_liste"]
    assert pays["status"] == ControlStatus.INCOHERENT
    assert pays["comparison"]["annonce"] == 12
    assert pays["comparison"]["identifies"] == 3


def test_every_computed_check_is_marked_as_a_proposal(client, dossier):
    assert _import(client, dossier, [DOSSIER_COMPLET]).status_code == 201
    checks = client.get(
        f"/api/v1/dossiers/{dossier['id']}/controle-administratif"
    ).json()["items"]
    computed = [check for check in checks if check["updated_by"] == "Analyse automatique"]
    assert computed
    for check in computed:
        assert check["explanation"].startswith(
            "Proposition de l'analyse — à confirmer par l'évaluateur."
        )


# --------------------------------------------------------------------------
# Analyse complète
# --------------------------------------------------------------------------


def test_full_analysis_runs_every_step(client, dossier):
    assert _import(client, dossier, [DOSSIER_COMPLET, PAGE_PROGRAMME]).status_code == 201
    result = client.post(f"/api/v1/dossiers/{dossier['id']}/analyse-complete").json()

    steps = {step["etape"] for step in result["steps"]}
    assert steps == {
        "OCR local",
        "Extraction des informations",
        "Repérage des pièces",
        "Contrôles administratifs",
        "Moteur de vigilance",
        "Registre de preuves",
        "Constats réglementaires",
        "Score scientifique",
        "Avis technique proposé",
        "Recherche publique",
    }
    assert result["web_run_id"], "les requêtes publiques doivent être préparées"
    # Le score et l'avis sont désormais proposés, mais restent des propositions.
    assert "aide à la décision" in result["notice"]
    assert "ne valent pas décision officielle" in result["notice"]


def test_full_analysis_proposes_score_and_avis_without_deciding(client, dossier):
    """Le score et l'avis sont proposés ; la décision reste à l'évaluateur."""
    assert _import(client, dossier, [DOSSIER_COMPLET]).status_code == 201
    result = client.post(f"/api/v1/dossiers/{dossier['id']}/analyse-complete").json()

    assessment = result["assessment"]
    assert 0 <= assessment["score"]["total"] <= 100
    assert assessment["decision"]["avis"] in {
        "FAVORABLE",
        "FAVORABLE_SOUS_RESERVES",
        "AJOURNEMENT_POUR_COMPLEMENTS",
        "REQUALIFICATION_NATIONALE_A_EXAMINER",
        "TRANSMISSION_TUTELLE_AVEC_ALERTE_MOTIVEE",
        "NON_DETERMINABLE_INFORMATION_INSUFFISANTE",
    }
    assert "ne valant pas décision officielle" in assessment["decision"]["disclaimer"]

    # La grille officielle saisie par l'évaluateur reste vierge : les deux
    # notations ne sont jamais confondues.
    evaluation = client.get(f"/api/v1/dossiers/{dossier['id']}/evaluation").json()
    assert evaluation["total"] is None
    assert all(row["score"] is None for row in evaluation["criteria"])

    # Aucune conclusion n'est écrite à la place de l'évaluateur.
    notes = client.get(f"/api/v1/dossiers/{dossier['id']}/notes").json()["items"]
    assert not [note for note in notes if note["kind"] == "CONCLUSION"]


def test_prepared_queries_are_not_sent_without_approval(client, dossier):
    assert _import(client, dossier, [DOSSIER_COMPLET]).status_code == 201
    result = client.post(f"/api/v1/dossiers/{dossier['id']}/analyse-complete").json()

    run = client.get(f"/api/v1/recherche-web/{result['web_run_id']}").json()
    assert run["queries"], "des requêtes doivent être proposées"
    for query in run["queries"]:
        assert query["approved"] is False
        assert query["sent_at"] is None
    assert run["sources"] == []


def test_regulation_references_are_captured_in_full():
    """Une référence « 595/SG du 19 mai 2025 » ne doit pas être tronquée."""
    from app.services.extraction_service import REGULATION_REF

    text = (
        "Références : Envoi n° 595/SG du 19 mai 2025 ; Loi n° 18-07 ; "
        "Envoi n° 218/DCEU-SDPUR du 14 juillet 2026"
    )
    assert [match.group(0) for match in REGULATION_REF.finditer(text)] == [
        "Envoi n° 595/SG du 19 mai 2025",
        "Loi n° 18-07",
        "Envoi n° 218/DCEU-SDPUR du 14 juillet 2026",
    ]
