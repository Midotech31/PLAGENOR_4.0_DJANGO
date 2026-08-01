"""ACC-004 / ACC-005 / ACC-007 : moteur de vigilance, règles inactives, contradictions."""

from __future__ import annotations

from app.core.vocabulary import FindingStatus, Priority
from app.services import rules_engine
from tests.fixtures import synthetic


def _import(client, dossier, content: bytes, name: str = "dossier.pdf"):
    return client.post(
        f"/api/v1/dossiers/{dossier['id']}/documents",
        files={"file": (name, content, "application/pdf")},
    )


def _findings(client, dossier, category: str | None = None):
    params = {"category": category} if category else None
    return client.get(f"/api/v1/dossiers/{dossier['id']}/alertes", params=params).json()["items"]


def test_explicit_maroc_mention_creates_contextualised_alert(client, dossier):
    assert _import(client, dossier, synthetic.make_pdf([synthetic.MAROC_AFFILIATION_TEXT])).status_code == 201
    findings = _findings(client, dossier, "MENTIONS_MAROC")
    assert findings, "une mention explicite du Maroc doit produire une alerte"
    finding = findings[0]
    assert finding["label"] == "Mentions relatives au Maroc — vérification institutionnelle obligatoire"
    assert "Point de vigilance institutionnelle" in finding["recommended_check"]
    assert finding["human_status"] == FindingStatus.A_VERIFIER
    assert finding["page_no"] == 1
    assert finding["context"]
    # Aucune décision, aucune interdiction.
    assert "ne constitue ni une décision" in finding["explanation"]


def test_indirect_moroccan_institution_is_detected_with_context(client, dossier):
    text = "Partenaire : Universite de Rabat, laboratoire associe. Affiliation declaree du conferencier."
    assert _import(client, dossier, synthetic.make_pdf([text])).status_code == 201
    findings = _findings(client, dossier, "MENTIONS_MAROC")
    assert any(item["trigger"].lower() == "rabat" for item in findings)
    secondary = next(item for item in findings if item["trigger"].lower() == "rabat")
    assert secondary["confidence"] < 0.9
    assert "ne prouve jamais à lui seul" in secondary["explanation"]


def test_city_without_institutional_context_is_not_flagged(client, dossier):
    """Faux positif à éviter : une ville seule ne déclenche rien."""
    assert _import(client, dossier, synthetic.make_pdf([synthetic.MAROC_FAUX_POSITIF_TEXT])).status_code == 201
    findings = _findings(client, dossier, "MENTIONS_MAROC")
    assert all(item["trigger"].lower() != "casablanca" for item in findings)


def test_bibliography_mention_is_flagged_but_qualifiable(client, dossier):
    assert _import(client, dossier, synthetic.make_pdf([synthetic.MAROC_BIBLIOGRAPHIE_TEXT])).status_code == 201
    findings = _findings(client, dossier, "MENTIONS_MAROC")
    assert findings
    response = client.post(
        f"/api/v1/dossiers/{dossier['id']}/alertes/{findings[0]['id']}",
        json={
            "status": FindingStatus.ECARTE,
            "comment": "Simple reference bibliographique, aucun lien institutionnel.",
            "relation_kind": "REFERENCE_BIBLIOGRAPHIQUE",
        },
    )
    assert response.status_code == 200
    assert response.json()["relation_kind"] == "REFERENCE_BIBLIOGRAPHIQUE"


def test_absence_of_maroc_mention_produces_no_alert(client, dossier):
    assert _import(client, dossier, synthetic.make_pdf([synthetic.ENGLISH_TEXT])).status_code == 201
    assert _findings(client, dossier, "MENTIONS_MAROC") == []
    notice = client.get(f"/api/v1/dossiers/{dossier['id']}/alertes").json()["notice"]
    assert "absence d'alerte ne prouve pas l'absence de risque" in notice


def test_sahara_and_cartography_alert(client, dossier):
    assert _import(client, dossier, synthetic.make_pdf([synthetic.SAHARA_TEXT])).status_code == 201
    findings = _findings(client, dossier, "INTEGRITE_TERRITORIALE")
    assert findings
    assert findings[0]["priority"] in {Priority.ELEVE, Priority.CRITIQUE}


def test_unreadable_page_produces_coverage_alert(client, dossier):
    """Une page illisible pouvant contenir un terme sensible est signalée."""
    assert _import(client, dossier, synthetic.make_scanned_pdf()).status_code == 201
    findings = _findings(client, dossier, "COUVERTURE_ANALYSE")
    assert findings
    assert "peut contenir un terme sensible non détecté" in findings[0]["explanation"]


def test_qualification_requires_motivation(client, dossier):
    assert _import(client, dossier, synthetic.make_pdf([synthetic.MAROC_AFFILIATION_TEXT])).status_code == 201
    finding = _findings(client, dossier, "MENTIONS_MAROC")[0]
    refused = client.post(
        f"/api/v1/dossiers/{dossier['id']}/alertes/{finding['id']}",
        json={"status": FindingStatus.CONFIRME, "comment": "court"},
    )
    assert refused.status_code == 422
    assert "motivation" in refused.json()["error"]["message"].lower()


def test_normative_rules_are_inactive_without_validated_source(client):
    """ACC-004 : une règle issue d'une source absente ou non adoptée reste inactive."""
    rules = {rule["code"]: rule for rule in client.get("/api/v1/regles").json()["items"]}
    for code in ("NORM-FORMAT-050", "NORM-SESSION-FREQ"):
        assert rules[code]["active"] is False
        assert rules[code]["is_normative"] is True
        assert rules[code]["presentable_as_prohibition"] is False


def test_activating_normative_rule_without_regulation_is_refused(client):
    response = client.post(
        "/api/v1/regles/NORM-FORMAT-050",
        json={"active": True, "reason": "Tentative d'activation sans texte officiel."},
    )
    assert response.status_code == 422
    assert "texte officiel validé" in response.json()["error"]["message"]


def test_vigilance_rules_never_claim_to_be_prohibitions(client):
    rules = client.get("/api/v1/regles").json()
    vigilance = [rule for rule in rules["items"] if not rule["is_normative"]]
    assert vigilance
    for rule in vigilance:
        assert rule["source_ref"] == "À confirmer par le Professeur Merzoug Mohamed ou par la commission"
        assert rule["presentable_as_prohibition"] is False
    assert "jamais être présentée comme une interdiction" in rules["notice"]


def test_conflicts_require_human_arbitration(client):
    """ACC-005 : les variantes contradictoires produisent CONTRADICTION_A_ARBITRER."""
    conflicts = {item["conflict_id"]: item for item in client.get("/api/v1/contradictions").json()["items"]}
    assert conflicts["CTR-SESSION-001"]["required_output"] == "CONTRADICTION_A_ARBITRER"
    assert conflicts["CTR-FORMAT-001"]["required_output"] == "CONTRADICTION_A_ARBITRER"
    for conflict in conflicts.values():
        if not conflict["arbitrated"]:
            assert "interprétation humaine obligatoire" in conflict["message"]
            assert len(conflict["sources"]) >= 2


def test_conflict_arbitration_requires_written_motivation(client):
    short = client.post(
        "/api/v1/contradictions/CTR-FORMAT-001",
        json={"note": "ok", "arbitrated_by": "Prof. Merzoug Mohamed"},
    )
    assert short.status_code == 422
    accepted = client.post(
        "/api/v1/contradictions/CTR-FORMAT-001",
        json={
            "note": "Instruction ecrite recue : le seuil de 50 % ne s'applique pas a cette session.",
            "arbitrated_by": "Prof. Merzoug Mohamed",
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["arbitrated"] is True


def test_rule_matching_uses_word_boundaries():
    spec = rules_engine.RuleSpec(
        code="TEST-001",
        category="TEST",
        label="Test",
        priority=Priority.MOYEN,
        terms=("visa",),
        secondary_terms=(),
        context_terms=(),
        guidance="Vérifier.",
        source_ref="À confirmer par le Professeur Merzoug Mohamed ou par la commission",
        version="1.0",
        is_normative=False,
    )
    assert rules_engine.scan_page(spec, 1, "Le visa est requis.")
    # « visage » ne doit pas déclencher la règle « visa ».
    assert not rules_engine.scan_page(spec, 1, "Le visage du participant.")


def test_arabic_and_accent_normalisation_matches():
    spec = rules_engine.RuleSpec(
        code="TEST-002",
        category="TEST",
        label="Test",
        priority=Priority.MOYEN,
        terms=("Fès", "المغرب"),
        secondary_terms=(),
        context_terms=(),
        guidance="Vérifier.",
        source_ref="À confirmer par le Professeur Merzoug Mohamed ou par la commission",
        version="1.0",
        is_normative=False,
    )
    assert rules_engine.scan_page(spec, 1, "Conference tenue a Fes.")
    assert rules_engine.scan_page(spec, 2, "الشريك من المغرب")


def test_alert_never_changes_score_or_status(client, dossier):
    """ACC-007 : une alerte ne produit ni note, ni conclusion, ni changement d'état."""
    assert _import(client, dossier, synthetic.make_pdf([synthetic.MAROC_AFFILIATION_TEXT])).status_code == 201
    before = client.get(f"/api/v1/dossiers/{dossier['id']}").json()
    finding = _findings(client, dossier, "MENTIONS_MAROC")[0]
    client.post(
        f"/api/v1/dossiers/{dossier['id']}/alertes/{finding['id']}",
        json={"status": FindingStatus.CONFIRME, "comment": "Affiliation confirmee a verifier."},
    )
    after = client.get(f"/api/v1/dossiers/{dossier['id']}").json()
    assert after["score_total"] == before["score_total"] is None
    assert after["status"] == before["status"]


def test_forbidden_automatic_status_is_refused(client, dossier):
    for value in ("ACCEPTE", "REJETE", "INTERDIT"):
        response = client.post(
            f"/api/v1/dossiers/{dossier['id']}/etat", json={"status": value}
        )
        assert response.status_code >= 400
