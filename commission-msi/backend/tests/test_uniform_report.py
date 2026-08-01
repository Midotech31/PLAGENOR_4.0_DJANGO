"""Rapport harmonisé — conformité au modèle fourni par la commission.

Le modèle impose huit sections, un vocabulaire d'**orientation technique**
transmise au ministère, et une section 4.1 où les éléments relatifs au Maroc et
à Israël sont strictement informatifs. Ces tests verrouillent ces trois points,
plus les garde-fous qui ne dépendent d'aucun modèle : rien d'inventé, aucun
numéro de passeport, aucune décision présentée comme prise.

S'y ajoute la section 4.2, où la veille en ligne rend compte des rattachements
et activités publics des intervenants étrangers. Les tests qui la couvrent
portent autant sur ce qu'elle affiche que sur ce qu'elle refuse d'examiner :
sans énoncé des critères écartés, un lecteur prêterait à l'application un
profilage par l'origine que son propre référentiel lui interdit.
"""

from __future__ import annotations

from app.reports import uniform_report
from app.services import job_service, report_service
from tests.fixtures import synthetic

DOSSIER = """DEMANDE D'ORGANISATION D'UNE MANIFESTATION SCIENTIFIQUE INTERNATIONALE
Intitulé : Conference internationale fictive sur l'arganier
Type de manifestation : conference internationale
Dates : du 20 avril 2027 au 21 avril 2027
Lieu : Universite fictive d'Adrar
Format : hybride
Établissement organisateur : Universite Fictive d'Adrar
Structure porteuse : Laboratoire des ressources naturelles sahariennes
Responsable scientifique : Pr Bencheikh Abdelali
Comité scientifique : Pr Jean Dubois (France) ; Pr Karim Idrissi (Maroc) ; Pr Amina Belkacem (Algerie)
Conférenciers : Pr Zool Ismail
Pays représentés : Algerie, France, Maroc
Liste des conférenciers étrangers avec copies de leurs passeports : passeport N° AB1234567
Budget total : 4 000 000 DA
Financement : subvention de l'etablissement
Modalités de publication : actes indexes et numero special de revue
"""

SECTION_TITLES = [
    "Fiche d'information contrôlée",
    "Appréciation scientifique commune",
    "Matrice réglementaire uniforme",
    "Contrôle des intervenants étrangers",
    "Points de vigilance institutionnelle",
    "Compléments indispensables avant appréciation ministérielle",
    "Orientation technique motivée transmise au ministère",
    "Sources et traçabilité",
]


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


def _flatten(model) -> str:
    parts: list[str] = [model.heading, model.subtitle]
    if model.headline:
        parts += [model.headline.title, model.headline.body]
    for section in model.sections:
        parts.append(f"{section.number}. {section.title}")
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


# --------------------------------------------------------------------------
# Structure imposée par le modèle
# --------------------------------------------------------------------------


def test_the_eight_sections_follow_the_model_order(client, dossier, session):
    _prepare(client, dossier)
    model = uniform_report.build(session, dossier["id"])

    assert model.heading == "RAPPORT D'ÉVALUATION HARMONISÉ"
    assert [section.number for section in model.sections] == list("12345678")
    assert [section.title for section in model.sections] == SECTION_TITLES


def test_the_header_names_the_assessed_piece(client, dossier, session):
    _prepare(client, dossier)
    model = uniform_report.build(session, dossier["id"])

    assert "Pièce évaluée : dossier.pdf" in model.subtitle
    # Les balises de statut restent dans les tableaux, pas dans le titre.
    assert "[A_VERIFIER]" not in model.subtitle


def test_the_orientation_is_shown_at_the_top_with_the_ministry_as_decider(
    client, dossier, session
):
    _prepare(client, dossier)
    model = uniform_report.build(session, dossier["id"])

    assert model.headline is not None
    assert model.headline.title.startswith("ORIENTATION TECHNIQUE PROPOSÉE — ")
    assert model.headline.body == "Décision finale : ministère."
    # Le libellé lisible porte ses accents.
    assert "COMPLEMENTS" not in model.headline.title


def test_the_scientific_table_has_five_dimensions_and_a_total(client, dossier, session):
    _prepare(client, dossier)
    model = uniform_report.build(session, dossier["id"])

    table = next(
        block.table for block in model.sections[1].blocks if block.kind == "table"
    )
    assert table.headers == ["Dimension", "Max.", "Note", "Motif probant"]
    assert len(table.rows) == 6, "cinq dimensions plus la ligne de total"
    assert table.rows[-1][0] == "TOTAL SCIENTIFIQUE"
    assert table.rows[-1][1] == "100"
    # Le total est bien la somme des cinq dimensions.
    assert int(table.rows[-1][2]) == sum(int(row[2]) for row in table.rows[:-1])
    for row in table.rows:
        assert row[3].strip(), f"motif probant manquant pour {row[0]}"


def test_the_matrix_uses_the_short_common_labels_of_the_model(client, dossier, session):
    _prepare(client, dossier)
    model = uniform_report.build(session, dossier["id"])

    table = next(
        block.table for block in model.sections[2].blocks if block.kind == "table"
    )
    assert table.headers == [
        "Réf.",
        "Critère commun",
        "État",
        "Constat / preuve au dossier",
        "Fondement",
    ]
    assert len(table.rows) == 26
    rows = {row[0]: row for row in table.rows}
    assert rows["I3"][1] == "Composante internationale du comité ≥ 20 %"
    assert rows["I7"][1] == "Internationaux ≈ 10 % des intervenants en personne"
    for row in table.rows:
        assert all(cell and cell.strip() for cell in row), f"cellule vide sur {row[0]}"
    assert "C = conforme démontré" in (table.note or "")


def test_section_four_one_covers_morocco_and_israel_as_information_only(
    client, dossier, session
):
    _prepare(client, dossier)
    model = uniform_report.build(session, dossier["id"])

    headings = [
        block.text for block in model.sections[3].blocks if block.kind == "subheading"
    ]
    assert headings == [
        "4.1. Éléments relatifs au Maroc et à Israël — information au ministère",
        "4.2. Contrôle en ligne des profils — rattachements et activités publics",
    ]

    boxes = [block.box for block in model.sections[3].blocks if block.kind == "box"]
    scopes = " ".join(box.body for box in boxes)
    # Le caractère strictement informatif est écrit noir sur blanc.
    assert "à titre strictement informatif" in scopes
    assert "ne constitue pas automatiquement une non-conformité" in scopes
    assert "relèvent exclusivement du ministère" in scopes
    assert "ne constitue pas une habilitation de sécurité" in scopes


def test_the_complements_are_short_actions_not_a_second_matrix(client, dossier, session):
    """La section 6 dit quoi produire ; le constat détaillé reste en section 3."""
    _prepare(client, dossier)
    model = uniform_report.build(session, dossier["id"])

    items = [
        item for block in model.sections[5].blocks if block.kind == "list" for item in block.items
    ]
    assert items
    for item in items:
        assert len(item) < 120, f"complément trop verbeux : {item}"
        assert any(
            action in item for action in ("à produire", "à documenter", "à compléter")
        )


def test_the_decision_section_speaks_of_orientation_never_of_a_decision(
    client, dossier, session
):
    _prepare(client, dossier)
    model = uniform_report.build(session, dossier["id"])
    rendered = _flatten(model)

    assert "l'appréciation et la décision finales appartiennent au ministère" in rendered
    assert "aide technique à l'instruction" in rendered


def test_sources_carry_the_versions_and_the_evidence_principle(client, dossier, session):
    _prepare(client, dossier)
    rendered = _flatten(uniform_report.build(session, dossier["id"]))

    assert "Référentiel réglementaire appliqué : version" in rendered
    assert "Grille scientifique appliquée : version" in rendered
    assert "SHA-256" in rendered
    assert "aucune déduction à partir de la nationalité, de l'origine" in rendered


# --------------------------------------------------------------------------
# Garde-fous indépendants du modèle
# --------------------------------------------------------------------------


def test_no_passport_number_is_ever_reproduced(client, dossier, session):
    _prepare(client, dossier)
    rendered = _flatten(uniform_report.build(session, dossier["id"]))

    assert "AB1234567" not in rendered


def test_a_dossier_without_analysis_says_so_instead_of_inventing(client, dossier, session):
    client.post(
        f"/api/v1/dossiers/{dossier['id']}/documents",
        files={"file": ("dossier.pdf", synthetic.make_pdf([DOSSIER]), "application/pdf")},
    )
    model = uniform_report.build(session, dossier["id"])

    assert model.headline.title == "ORIENTATION TECHNIQUE — NON ENCORE ÉTABLIE"
    assert uniform_report.NO_ASSESSMENT in _flatten(model)


# --------------------------------------------------------------------------
# Mise en page et intégration
# --------------------------------------------------------------------------


def test_the_harmonised_layout_is_the_default_and_fits_three_pages(client, dossier):
    _prepare(client, dossier)
    report = client.post(
        f"/api/v1/dossiers/{dossier['id']}/rapports", json={"format": "pdf"}
    ).json()

    assert report["layout"] == "harmonise"
    # Le modèle vise trois pages ; on vérifie que le format y parvient
    # réellement, sans avoir rien retiré du contenu imposé.
    assert report["page_count"] <= 3, f"{report['page_count']} pages rendues"


def test_the_harmonised_layout_produces_a_valid_docx(client, dossier):
    _prepare(client, dossier)
    created = client.post(
        f"/api/v1/dossiers/{dossier['id']}/rapports",
        json={"format": "docx", "layout": "harmonise"},
    ).json()
    content = client.get(
        f"/api/v1/dossiers/{dossier['id']}/rapports/{created['id']}/fichier"
    ).content

    assert content[:2] == b"PK"


def test_the_other_layouts_remain_available(client, dossier):
    _prepare(client, dossier)
    for layout in ("compact", "detaille"):
        response = client.post(
            f"/api/v1/dossiers/{dossier['id']}/rapports",
            json={"format": "docx", "layout": layout},
        )
        assert response.status_code == 201, layout
        assert response.json()["layout"] == layout


def test_the_downloaded_file_is_named_for_filing_not_for_machines(client, dossier):
    """Un identifiant technique ne se classe pas dans un dossier de commission."""
    _prepare(client, dossier)
    created = client.post(
        f"/api/v1/dossiers/{dossier['id']}/rapports", json={"format": "pdf"}
    ).json()

    response = client.get(
        f"/api/v1/dossiers/{dossier['id']}/rapports/{created['id']}/fichier"
    )
    disposition = response.headers["content-disposition"]
    assert "attachment" in disposition
    assert dossier["reference"] in disposition
    assert "brouillon" in disposition
    assert dossier["id"] not in disposition


# --------------------------------------------------------------------------
# 4.2 Contrôle en ligne des profils
# --------------------------------------------------------------------------


def _record_screening_claim(session, dossier_id: str, statement: str, *, sources: int = 2):
    """Dépose un constat de l'agent de souveraineté, comme le ferait une veille."""
    import json

    from app.agents.sovereignty import INFORMATIVE_ONLY
    from app.core.crypto import encrypt_text
    from app.core.keyring import get_master_key
    from app.core.vocabulary import AgentName, ClaimNature, EvidenceStatus, WebRunStatus
    from app.models.web_entities import OnlineClaim, WebResearchRun
    from app.web_research.service import claim_aad

    run = WebResearchRun(dossier_id=dossier_id, status=WebRunStatus.TERMINEE)
    session.add(run)
    session.flush()

    record = OnlineClaim(
        run_id=run.id,
        dossier_id=dossier_id,
        agent_name=AgentName.SOUVERAINETE_NATIONALE,
        subject_label="Pr Jean Dubois",
        statement_cipher=b"",
        nature=ClaimNature.FAIT_VERIFIE,
        status=EvidenceStatus.SOURCES_CONCORDANTES,
        confidence=0.8,
        source_ids_json=json.dumps(["https://a.example/p", "https://b.example/q"]),
        independent_source_count=sources,
    )
    session.add(record)
    session.flush()
    record.statement_cipher = encrypt_text(
        get_master_key(), f"{statement}\n{INFORMATIVE_ONLY}", claim_aad(record.id, "statement")
    )
    session.commit()


def test_the_online_screening_has_its_own_subsection(client, dossier, session):
    _prepare(client, dossier)
    model = uniform_report.build(session, dossier["id"])

    text = _flatten(model)
    assert "4.2. Contrôle en ligne des profils" in text


def test_without_a_web_run_the_screening_says_so_rather_than_reassuring(
    client, dossier, session
):
    """Ne pas avoir cherché n'est pas n'avoir rien trouvé."""
    _prepare(client, dossier)
    model = uniform_report.build(session, dossier["id"])

    text = _flatten(model)
    assert "la veille en ligne n'a pas été exécutée" in text
    assert "ni un constat favorable, ni un constat défavorable" in text


def test_a_documented_element_is_tabled_with_its_level_of_proof(client, dossier, session):
    _prepare(client, dossier)
    _record_screening_claim(
        session,
        dossier["id"],
        "Un rattachement en lien avec « Bar-Ilan » est documenté publiquement.",
    )
    model = uniform_report.build(session, dossier["id"])

    table = next(
        block.table
        for block in model.sections[3].blocks
        if block.kind == "table" and "profils publics" in block.table.caption
    )
    assert table.headers == ["Personne", "Élément relevé", "Sources indép.", "Niveau de preuve"]
    assert table.rows[0][0] == "Pr Jean Dubois"
    assert "Bar-Ilan" in table.rows[0][1]
    assert table.rows[0][2] == "2"
    # La mention de portée n'encombre pas la cellule : elle est dans l'encadré.
    assert "strictement informatif" not in table.rows[0][1]


def test_the_screening_states_the_criteria_it_refuses_to_apply(client, dossier, session):
    """Sans cet énoncé, un lecteur pourrait croire à un profilage par l'origine."""
    _prepare(client, dossier)
    model = uniform_report.build(session, dossier["id"])

    text = _flatten(model)
    for forbidden in (
        "la nationalité",
        "l'origine ethnique",
        "la religion",
        "le lieu de naissance",
        "la consonance d'un nom",
        "une opinion supposée",
    ):
        assert forbidden in text, forbidden
    assert "n'est pas une garantie et ne constitue pas une habilitation de sécurité" in text


def test_the_screening_never_presents_an_element_as_a_non_conformity(client, dossier, session):
    _prepare(client, dossier)
    _record_screening_claim(
        session, dossier["id"], "Un rattachement institutionnel est documenté publiquement."
    )
    model = uniform_report.build(session, dossier["id"])

    text = _flatten(model)
    assert "aucun n'est qualifié par l'application" in text
    assert "non-conformité" not in _screening_rows(model)


def _screening_rows(model) -> str:
    table = next(
        block.table
        for block in model.sections[3].blocks
        if block.kind == "table" and "profils publics" in block.table.caption
    )
    return "\n".join("\n".join(row) for row in table.rows)
