"""ACC-003 / ACC-006 / ACC-008 / ACC-015 : provenance, grille, rapport, porte G7."""

from __future__ import annotations

from app.core.vocabulary import Conclusion, ControlStatus, FindingStatus, InformationStatus, PieceStatus
from tests.fixtures import synthetic

GOOD_JUSTIFICATION = "Justification detaillee fondee sur les pages 1 et 2 du dossier fictif."


def _import(client, dossier, content=None):
    content = content or synthetic.make_pdf([synthetic.NATIVE_TEXT_FR])
    return client.post(
        f"/api/v1/dossiers/{dossier['id']}/documents",
        files={"file": ("dossier.pdf", content, "application/pdf")},
    )


def _items(client, dossier):
    return client.get(f"/api/v1/dossiers/{dossier['id']}/informations").json()["items"]


def test_fact_without_source_is_refused(client, dossier):
    """ACC-003 : enregistrement factuel refusé sans document, page ou passage."""
    _import(client, dossier)
    item = next(item for item in _items(client, dossier) if item["key"] == "lieu")
    response = client.post(
        f"/api/v1/dossiers/{dossier['id']}/informations/{item['id']}",
        json={
            "value": "Campus fictif",
            "status": InformationStatus.CONFIRME,
            "reason": "Confirme apres lecture.",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PROVENANCE_REQUISE"

    audit = client.get("/api/v1/audit").json()["items"]
    assert audit, "le refus doit rester traçable dans le journal"


def test_fact_with_page_and_excerpt_is_accepted(client, dossier):
    _import(client, dossier)
    item = next(item for item in _items(client, dossier) if item["key"] == "lieu")
    response = client.post(
        f"/api/v1/dossiers/{dossier['id']}/informations/{item['id']}",
        json={
            "value": "Campus fictif, Alger",
            "status": InformationStatus.CONFIRME,
            "reason": "Confirme depuis la fiche technique.",
            "page_no": 1,
            "source_excerpt": "Lieu : Campus fictif, Alger",
        },
    )
    assert response.status_code == 200
    assert response.json()["page_no"] == 1


def test_manual_entry_must_be_explicitly_validated(client, dossier):
    _import(client, dossier)
    item = next(item for item in _items(client, dossier) if item["key"] == "theme")
    response = client.post(
        f"/api/v1/dossiers/{dossier['id']}/informations/{item['id']}",
        json={
            "value": "Materiaux durables",
            "status": InformationStatus.CONFIRME,
            "reason": "Saisie manuelle validee par l'evaluateur.",
            "manual_entry_validated": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["extraction_mode"] == "SAISIE_MANUELLE"


def test_reinforced_control_flags_are_present(client, dossier):
    reinforced = {item["key"] for item in _items(client, dossier) if item["reinforced_control"]}
    for key in ("date_debut", "montants_devise", "pays_representes", "intervenants"):
        assert key in reinforced


def test_score_out_of_bounds_is_refused(client, dossier):
    """ACC-006 : pas de note hors limites, pas de valeur de remplacement."""
    response = client.post(
        f"/api/v1/dossiers/{dossier['id']}/evaluation",
        json={
            "criterion_key": "pertinence_priorites",
            "score": 31,
            "justification": GOOD_JUSTIFICATION,
        },
    )
    assert response.status_code == 422
    assert "hors bornes" in response.json()["error"]["message"]
    assert "Aucune valeur de remplacement" in response.json()["error"]["message"]


def test_score_without_justification_is_refused(client, dossier):
    response = client.post(
        f"/api/v1/dossiers/{dossier['id']}/evaluation",
        json={"criterion_key": "pertinence_priorites", "score": 20, "justification": "court"},
    )
    assert response.status_code == 422


def test_total_is_blocked_until_grid_is_complete(client, dossier):
    state = client.get(f"/api/v1/dossiers/{dossier['id']}/evaluation").json()
    assert state["total"] is None
    assert "Le système ne propose aucune note" in state["notice"]

    client.post(
        f"/api/v1/dossiers/{dossier['id']}/evaluation",
        json={
            "criterion_key": "pertinence_priorites",
            "score": 25,
            "justification": GOOD_JUSTIFICATION,
        },
    )
    partial = client.get(f"/api/v1/dossiers/{dossier['id']}/evaluation").json()
    assert partial["total"] is None
    assert len(partial["missing"]) == 4


def _complete_grid(client, dossier):
    scores = {
        "pertinence_priorites": 25,
        "objectifs_resultats_retombes": 16,
        "cooperation_internationale": 15,
        "faisabilite_gouvernance_financement": 12,
        "valorisation_publications_suivi": 11,
    }
    for key, score in scores.items():
        response = client.post(
            f"/api/v1/dossiers/{dossier['id']}/evaluation",
            json={
                "criterion_key": key,
                "score": score,
                "justification": GOOD_JUSTIFICATION,
                "source_pages": [1],
            },
        )
        assert response.status_code == 200
    return sum(scores.values())


def test_total_is_only_a_sum_of_entered_scores(client, dossier):
    expected = _complete_grid(client, dossier)
    state = client.get(f"/api/v1/dossiers/{dossier['id']}/evaluation").json()
    assert state["complete"] is True
    assert state["total"] == expected
    assert state["max_total"] == 100
    assert "simple somme" in state["notice"]


def test_score_history_is_kept(client, dossier):
    for score in (10, 20):
        client.post(
            f"/api/v1/dossiers/{dossier['id']}/evaluation",
            json={
                "criterion_key": "pertinence_priorites",
                "score": score,
                "justification": GOOD_JUSTIFICATION,
            },
        )
    events = client.get("/api/v1/audit", params={"action": "EVALUATION_ENTRY"}).json()["items"]
    assert len(events) >= 2


def test_conclusion_requires_closed_list_and_motivation(client, dossier):
    invalid = client.post(
        f"/api/v1/dossiers/{dossier['id']}/conclusion",
        json={"conclusion": "AVIS_DEFINITIF", "motivation": GOOD_JUSTIFICATION},
    )
    assert invalid.status_code == 422

    short = client.post(
        f"/api/v1/dossiers/{dossier['id']}/conclusion",
        json={"conclusion": Conclusion.AVIS_FAVORABLE_SOUS_RESERVES, "motivation": "court"},
    )
    assert short.status_code == 422

    valid = client.post(
        f"/api/v1/dossiers/{dossier['id']}/conclusion",
        json={
            "conclusion": Conclusion.AVIS_FAVORABLE_SOUS_RESERVES,
            "motivation": "Motivation personnelle detaillee de l'evaluateur sur le dossier fictif.",
        },
    )
    assert valid.status_code == 201
    assert "ne vaut pas décision de la commission" in valid.json()["notice"]


def _qualify_everything(client, dossier):
    for piece in client.get(f"/api/v1/dossiers/{dossier['id']}/pieces").json()["items"]:
        client.post(
            f"/api/v1/dossiers/{dossier['id']}/pieces/{piece['id']}",
            json={
                "status": PieceStatus.NON_APPLICABLE,
                "comment": "Piece non applicable au dossier fictif de test.",
            },
        )
    for finding in client.get(f"/api/v1/dossiers/{dossier['id']}/alertes").json()["items"]:
        client.post(
            f"/api/v1/dossiers/{dossier['id']}/alertes/{finding['id']}",
            json={"status": FindingStatus.ECARTE, "comment": "Ecartee apres verification humaine."},
        )
    for check in client.get(f"/api/v1/dossiers/{dossier['id']}/controle-administratif").json()["items"]:
        client.post(
            f"/api/v1/dossiers/{dossier['id']}/controle-administratif/{check['id']}",
            json={
                "status": ControlStatus.CONFIRME,
                "explanation": "Controle effectue sur le dossier fictif.",
            },
        )


def test_draft_report_is_watermarked_and_official_export_is_blocked(client, dossier):
    """ACC-015 : sans validation G7, seul un brouillon peut être produit."""
    _import(client, dossier)
    draft = client.post(
        f"/api/v1/dossiers/{dossier['id']}/rapports", json={"format": "docx", "official": False}
    )
    assert draft.status_code == 201
    assert draft.json()["is_draft"] is True

    official = client.post(
        f"/api/v1/dossiers/{dossier['id']}/rapports", json={"format": "docx", "official": True}
    )
    assert official.status_code == 409
    assert "G7_VALIDATION_HUMAINE" in official.json()["error"]["message"]


def test_report_validation_requires_gates(client, dossier):
    _import(client, dossier)
    response = client.post(
        f"/api/v1/dossiers/{dossier['id']}/rapports/validation-humaine",
        json={"statement": "Je valide ce rapport apres relecture complete du dossier fictif."},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PORTE_NON_SATISFAITE"


def test_full_workflow_produces_valid_docx_and_pdf(client, dossier):
    """Scénario de bout en bout : import → qualification → grille → rapport officiel."""
    _import(client, dossier)
    _qualify_everything(client, dossier)
    _complete_grid(client, dossier)
    client.post(
        f"/api/v1/dossiers/{dossier['id']}/conclusion",
        json={
            "conclusion": Conclusion.TRANSMISSION_COMMISSION_AVEC_VIGILANCE,
            "motivation": "Transmission proposee avec les reserves detaillees dans le rapport.",
        },
    )
    validation = client.post(
        f"/api/v1/dossiers/{dossier['id']}/rapports/validation-humaine",
        json={"statement": "Je valide ce rapport apres relecture complete du dossier fictif."},
    )
    assert validation.status_code == 200, validation.text

    for fmt, magic in (("docx", b"PK"), ("pdf", b"%PDF")):
        created = client.post(
            f"/api/v1/dossiers/{dossier['id']}/rapports", json={"format": fmt, "official": True}
        )
        assert created.status_code == 201, created.text
        assert created.json()["is_draft"] is False
        downloaded = client.get(
            f"/api/v1/dossiers/{dossier['id']}/rapports/{created.json()['id']}/fichier"
        )
        assert downloaded.status_code == 200
        assert downloaded.content.startswith(magic)
        assert len(downloaded.content) > 2000


def test_report_model_labels_and_signature(client, dossier, session):
    from app.reports.builder import build_report_model

    _import(client, dossier)
    model = build_report_model(session, dossier["id"])
    # 18 sections imposées + la section dédiée au classement externe indicatif.
    assert len(model.sections) == 19
    assert model.sections[11].title.startswith("Mentions relatives au Maroc")
    ranking_section = model.sections[18]
    assert ranking_section.title.startswith("Classement externe indicatif assisté par IA")
    assert any(
        "ne modifie aucune note de la grille scientifique officielle" in line.text
        for line in ranking_section.lines
    )
    kinds = {line.kind for section in model.sections for line in section.lines}
    assert {"FAIT_EXTRAIT", "CALCUL", "A_VERIFIER"} <= kinds
    assert model.signature == "Designed by Prof. Merzoug Mohamed"
    assert model.banner == "Projet de rapport — validation humaine obligatoire"
    # Chaque ligne porte une source explicite.
    for section in model.sections:
        for line in section.lines:
            assert line.source_label in {"sans source", "saisie manuelle validée"} or line.source_label.startswith("page ")


def test_orphan_fact_is_excluded_from_official_export(client, dossier, session):
    """ACC-008 : un fait sans page ni saisie validée ne passe pas en export officiel."""
    from app.models import ExtractedItem
    from app.core.crypto import encrypt_text
    from app.core.keyring import get_master_key

    _import(client, dossier)
    _qualify_everything(client, dossier)
    _complete_grid(client, dossier)
    client.post(
        f"/api/v1/dossiers/{dossier['id']}/conclusion",
        json={
            "conclusion": Conclusion.AVIS_FAVORABLE,
            "motivation": "Motivation personnelle detaillee pour le dossier fictif de test.",
        },
    )
    client.post(
        f"/api/v1/dossiers/{dossier['id']}/rapports/validation-humaine",
        json={"statement": "Je valide ce rapport apres relecture complete du dossier fictif."},
    )

    # Injection directe d'un fait orphelin (contourne l'API, comme le ferait une régression).
    item = session.query(ExtractedItem).filter_by(dossier_id=dossier["id"], key="budget_total").one()
    item.current_value_cipher = encrypt_text(
        get_master_key(), "1 200 000 DA", f"item:{item.id}:current"
    )
    item.status = "CONFIRME"
    item.page_no = None
    item.manual_entry_validated = False
    session.commit()

    response = client.post(
        f"/api/v1/dossiers/{dossier['id']}/rapports", json={"format": "pdf", "official": True}
    )
    assert response.status_code == 409
    assert "sans page ni saisie" in response.json()["error"]["message"]


def test_gates_never_reject_the_dossier(client, dossier):
    _import(client, dossier)
    gates = client.get(f"/api/v1/dossiers/{dossier['id']}").json()["gates"]
    assert set(gates) == {
        "G0_SOURCE",
        "G1_EXTRACTION",
        "G2_ADMINISTRATIF",
        "G3_ELIGIBILITE",
        "G4_SCIENTIFIQUE",
        "G5_VIGILANCE",
        "G6_RAPPORT",
        "G7_VALIDATION_HUMAINE",
    }
    status = client.get(f"/api/v1/dossiers/{dossier['id']}").json()["status"]
    assert status not in {"ACCEPTE", "REJETE", "INTERDIT"}
