"""Rapport compact en trois pages (§15).

Ce que le rapport doit contenir, et surtout ce qu'il ne doit jamais contenir :
aucun numéro de passeport, aucune affirmation sans preuve, aucun avis présenté
comme une décision, et jamais un contenu tronqué pour tenir en trois pages.
"""

from __future__ import annotations

from app.reports import compact_report
from app.services import job_service, report_service
from tests.fixtures import synthetic

DOSSIER = """DEMANDE D'ORGANISATION D'UNE MANIFESTATION SCIENTIFIQUE INTERNATIONALE
Intitulé : Colloque international fictif sur les materiaux durables
Type de manifestation : colloque international
Dates : du 12 mars 2027 au 14 mars 2027
Lieu : Campus fictif, Alger
Format : hybride
Établissement organisateur : Universite Fictive de Test
Structure porteuse : Laboratoire fictif des materiaux
Responsable scientifique : Pr Amina Belkacem
Comité scientifique : Pr Jean Dubois (France) ; Pr Karim Idrissi (Maroc)
Comité d'organisation : Dr Sofiane Merabet
Conférenciers : Pr Zool Ismail
Pays représentés : Algerie, France, Maroc
Liste des conférenciers étrangers avec copies de leurs passeports : passeport N° AB1234567
Budget total : 1 000 000 DA
Financement : subvention de l'etablissement
Modalités de publication : actes indexes et numero special de revue
"""


def _prepare(client, dossier):
    assert (
        client.post(
            f"/api/v1/dossiers/{dossier['id']}/documents",
            files={"file": ("dossier.pdf", synthetic.make_pdf([DOSSIER]), "application/pdf")},
        ).status_code
        == 201
    )
    client.post(f"/api/v1/dossiers/{dossier['id']}/traitement")
    job_service.work_once()


def test_the_compact_report_has_exactly_the_three_required_sections(client, dossier, session):
    _prepare(client, dossier)
    model = compact_report.build(session, dossier["id"])

    assert [section.number for section in model.sections] == ["1", "2", "3"]
    assert model.sections[0].title == "Informations et appréciation scientifique"
    assert model.sections[1].title == "Matrice réglementaire — 26 critères"
    assert model.sections[2].title == "Vérifications, limites et conclusion"


def test_page_one_carries_the_score_and_the_visible_proposed_avis(client, dossier, session):
    _prepare(client, dossier)
    model = compact_report.build(session, dossier["id"])

    assert model.headline is not None
    assert "Avis technique proposé" in model.headline.title
    # L'avis est visible d'emblée, et présenté comme une proposition.
    assert "ne valant pas décision officielle" in model.headline.body

    tables = [block.table for block in model.sections[0].blocks if block.kind == "table"]
    captions = " ".join(table.caption for table in tables)
    assert "Identification du dossier" in captions
    assert "Grille scientifique" in captions


def test_page_two_lists_the_twenty_six_criteria_in_order_with_no_empty_cell(
    client, dossier, session
):
    _prepare(client, dossier)
    model = compact_report.build(session, dossier["id"])

    matrix = next(
        block.table for block in model.sections[1].blocks if block.kind == "table"
    )
    assert matrix.headers == [
        "Code",
        "Critère",
        "Statut",
        "Constat",
        "Preuve / page",
        "Fondement exact",
    ]
    assert len(matrix.rows) == 26
    assert [row[0] for row in matrix.rows][:4] == ["A1", "A2", "A3", "A4"]
    for row in matrix.rows:
        assert all(cell and cell.strip() for cell in row), f"cellule vide sur {row[0]}"


def test_page_three_covers_every_required_heading(client, dossier, session):
    _prepare(client, dossier)
    model = compact_report.build(session, dossier["id"])

    headings = {
        block.text for block in model.sections[2].blocks if block.kind == "subheading"
    }
    assert headings == {
        "Contrôle des intervenants étrangers",
        "Points de vigilance institutionnelle",
        "Contradictions et limites",
        "Compléments indispensables",
        "Avis motivé",
        "Sources, traçabilité, empreintes et versions",
    }


def test_no_passport_number_is_ever_reproduced(client, dossier, session):
    """La pièce restreinte est mentionnée ; son contenu ne l'est jamais."""
    _prepare(client, dossier)
    model = compact_report.build(session, dossier["id"])

    rendered = _flatten(model)
    assert "AB1234567" not in rendered
    assert "aucune adresse privée ni donnée personnelle inutile" in rendered.lower()


def test_the_report_states_the_versions_and_fingerprints_it_used(client, dossier, session):
    _prepare(client, dossier)
    rendered = _flatten(compact_report.build(session, dossier["id"]))

    assert "Référentiel réglementaire : version" in rendered
    assert "Grille scientifique : version" in rendered
    assert "SHA-256" in rendered


def test_the_compact_layout_is_the_default_and_produces_a_valid_docx_and_pdf(
    client, dossier, session
):
    _prepare(client, dossier)

    docx = client.post(
        f"/api/v1/dossiers/{dossier['id']}/rapports", json={"format": "docx"}
    ).json()
    assert docx["layout"] == "compact"
    content = client.get(
        f"/api/v1/dossiers/{dossier['id']}/rapports/{docx['id']}/fichier"
    ).content
    assert content[:2] == b"PK", "un DOCX est une archive ZIP"

    pdf = client.post(
        f"/api/v1/dossiers/{dossier['id']}/rapports",
        json={"format": "pdf", "layout": "compact"},
    ).json()
    rendered = client.get(
        f"/api/v1/dossiers/{dossier['id']}/rapports/{pdf['id']}/fichier"
    ).content
    assert rendered[:5] == b"%PDF-"


def test_the_detailed_layout_remains_available_when_evidence_requires_it(client, dossier):
    _prepare(client, dossier)
    detailed = client.post(
        f"/api/v1/dossiers/{dossier['id']}/rapports",
        json={"format": "docx", "layout": "detaille"},
    )
    assert detailed.status_code == 201
    assert detailed.json()["layout"] == "detaille"


def test_an_unknown_layout_is_refused(client, dossier):
    _prepare(client, dossier)
    response = client.post(
        f"/api/v1/dossiers/{dossier['id']}/rapports",
        json={"format": "docx", "layout": "resume-express"},
    )
    assert response.status_code == 422


def test_a_dossier_without_assessment_says_so_instead_of_inventing(client, dossier, session):
    """Sans analyse, le rapport le dit — il n'invente ni note ni avis."""
    client.post(
        f"/api/v1/dossiers/{dossier['id']}/documents",
        files={"file": ("dossier.pdf", synthetic.make_pdf([DOSSIER]), "application/pdf")},
    )
    model = compact_report.build(session, dossier["id"])
    rendered = _flatten(model)
    assert compact_report.NO_ASSESSMENT in rendered
    assert model.headline.title == "Avis technique — non encore établi"


def _flatten(model) -> str:
    parts: list[str] = []
    if model.headline:
        parts += [model.headline.title, model.headline.body]
    for section in model.sections:
        parts.append(section.title)
        for block in section.blocks:
            if block.kind == "table" and block.table:
                parts.append(block.table.caption)
                parts += block.table.headers
                for row in block.table.rows:
                    parts += row
                if block.table.note:
                    parts.append(block.table.note)
            elif block.kind == "paragraph" and block.paragraph:
                parts.append(block.paragraph.text)
            elif block.kind == "box" and block.box:
                parts += [block.box.title, block.box.body]
            elif block.kind == "list":
                parts += block.items
            elif block.kind == "subheading":
                parts.append(block.text)
    return "\n".join(parts)
