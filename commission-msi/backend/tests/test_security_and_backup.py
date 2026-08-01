"""ACC-009 à ACC-013, ACC-016 : démarrage, sécurité locale, chiffrement, sauvegarde."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from app.core import crypto
from app.core.security import resolve_within, safe_filename
from app.core.vocabulary import Sensitivity
from app.services import backup_service
from tests.conftest import LOCAL_BASE_URL
from tests.fixtures import synthetic


# --------------------------------------------------------------------------
# Démarrage direct (ACC-009)
# --------------------------------------------------------------------------


def test_dashboard_opens_directly_without_login(client):
    """Aucun compte, aucune route /setup, /login ou /logout."""
    for route in ("/api/v1/setup", "/api/v1/login", "/api/v1/logout"):
        assert client.post(route).status_code == 404
    dashboard = client.get("/api/v1/dossiers/tableau-de-bord")
    assert dashboard.status_code == 200
    assert "recent_dossiers" in dashboard.json()
    health = client.get("/api/v1/health").json()
    assert "aucune" in health["authentication"]


def test_no_authentication_tables_exist(session):
    from sqlalchemy import inspect

    tables = set(inspect(session.get_bind()).get_table_names())
    assert not tables & {"users", "sessions", "credentials", "accounts", "auth_tokens"}


def test_repeated_requests_never_redirect(client):
    for _ in range(3):
        response = client.get("/api/v1/readiness", follow_redirects=False)
        assert response.status_code == 200
        assert response.json()["ready"] is True


def test_readiness_reports_each_check(client):
    checks = client.get("/api/v1/readiness").json()["checks"]
    assert checks == {
        "database": True,
        "referential": True,
        "data_directory": True,
        "master_key": True,
    }


def test_port_probe_detects_occupied_port():
    from app.api.v1.system import port_is_free

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        port = occupied.getsockname()[1]
        assert port_is_free("127.0.0.1", port) is False
    assert port_is_free("127.0.0.1", 0) is True


# --------------------------------------------------------------------------
# Origine locale stricte
# --------------------------------------------------------------------------


def test_remote_host_header_is_refused(client):
    response = client.get("/api/v1/health", headers={"Host": "exemple.invalid"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGINE_NON_LOCALE"


def test_mutating_request_from_remote_origin_is_refused(client):
    response = client.post(
        "/api/v1/dossiers",
        json={"reference": "X-1", "title": "T", "organizer": "O"},
        headers={"Origin": "https://exemple.invalid"},
    )
    assert response.status_code == 403


def test_mutating_request_from_remote_referer_is_refused(client):
    response = client.post(
        "/api/v1/dossiers",
        json={"reference": "X-2", "title": "T", "organizer": "O"},
        headers={"Referer": "https://exemple.invalid/page"},
    )
    assert response.status_code == 403


def test_security_headers_are_applied(client):
    headers = client.get("/api/v1/health").headers
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert "connect-src 'self'" in headers["Content-Security-Policy"]
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"


def test_diagnostic_reports_local_only_binding(client):
    diagnostic = client.get("/api/v1/diagnostic").json()
    assert diagnostic["bind_host"] == "127.0.0.1"
    assert diagnostic["listens_locally_only"] is True
    assert "Aucune ressource Internet" in diagnostic["network_policy"]
    assert any("master.key" in note for note in diagnostic["security_notes"])
    assert any("BitLocker" in note for note in diagnostic["security_notes"])


# --------------------------------------------------------------------------
# Traversée de chemin et noms dangereux
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dangerous",
    ["../../etc/passwd", "..\\..\\windows\\system32", "/etc/shadow", "CON", "fichier\x00.pdf"],
)
def test_path_traversal_is_neutralised(tmp_path: Path, dangerous: str):
    resolved = resolve_within(tmp_path, dangerous)
    assert tmp_path.resolve() in resolved.parents
    assert ".." not in resolved.parts


def test_safe_filename_neutralises_reserved_names():
    assert safe_filename("../../evil.pdf") == "evil.pdf"
    assert safe_filename("CON.pdf").startswith("_")
    assert safe_filename("") == "document"


def test_uploaded_filename_is_sanitised(client, dossier):
    response = client.post(
        f"/api/v1/dossiers/{dossier['id']}/documents",
        files={
            "file": (
                "../../../evil name.pdf",
                synthetic.make_pdf([synthetic.NATIVE_TEXT_FR]),
                "application/pdf",
            )
        },
    )
    assert response.status_code == 201
    assert "/" not in response.json()["original_name"]
    assert ".." not in response.json()["original_name"]


# --------------------------------------------------------------------------
# Chiffrement (ACC-011 mauvaise clé)
# --------------------------------------------------------------------------


def test_aes_gcm_roundtrip_and_wrong_key_refused():
    key = crypto.generate_key()
    blob = crypto.encrypt(key, b"contenu fictif", "document:abc")
    assert crypto.decrypt(key, blob, "document:abc") == b"contenu fictif"

    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(crypto.generate_key(), blob, "document:abc")


def test_aad_binding_prevents_object_substitution():
    key = crypto.generate_key()
    blob = crypto.encrypt(key, b"texte de la page 1", "page:aaa:original")
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(key, blob, "page:bbb:original")


def test_truncated_blob_is_refused():
    key = crypto.generate_key()
    blob = crypto.encrypt(key, b"contenu", "x:1")
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(key, blob[:10], "x:1")


def test_stored_document_is_encrypted_on_disk(client, dossier, data_dir):
    content = synthetic.make_pdf([synthetic.NATIVE_TEXT_FR])
    client.post(
        f"/api/v1/dossiers/{dossier['id']}/documents",
        files={"file": ("d.pdf", content, "application/pdf")},
    )
    stored = list((data_dir / "documents").glob("*.enc"))
    assert stored
    raw = stored[0].read_bytes()
    assert not raw.startswith(b"%PDF-")
    assert b"Colloque international" not in raw


def test_master_key_is_never_regenerated(data_dir):
    from app.core.crypto import load_or_create_master_key

    path = data_dir / "master.key"
    first = load_or_create_master_key(path)
    assert load_or_create_master_key(path) == first


# --------------------------------------------------------------------------
# Données restreintes (ACC-012)
# --------------------------------------------------------------------------


def test_restricted_document_access_is_audited(client, dossier):
    created = client.post(
        f"/api/v1/dossiers/{dossier['id']}/documents",
        params={"sensitivity": Sensitivity.RESTREINT},
        files={
            "file": (
                "passeports.pdf",
                synthetic.make_pdf(["Liste fictive de passeports des conferenciers etrangers."]),
                "application/pdf",
            )
        },
    )
    assert created.status_code == 201
    assert created.json()["sensitivity"] == Sensitivity.RESTREINT
    client.get(f"/api/v1/dossiers/{dossier['id']}/documents/{created.json()['id']}/original")
    actions = {event["action"] for event in client.get("/api/v1/audit").json()["items"]}
    assert "RESTRICTED_ACCESS" in actions


def test_identity_piece_excerpt_is_masked(client, dossier):
    pieces = client.get(f"/api/v1/dossiers/{dossier['id']}/pieces").json()["items"]
    restricted = [piece for piece in pieces if piece["sensitivity"] == Sensitivity.RESTREINT]
    assert restricted
    for piece in restricted:
        assert piece["detection_excerpt"] in (None, "[Contenu restreint — documents d'identité]")


def test_audit_never_stores_clear_sensitive_values(client, dossier):
    client.post(
        f"/api/v1/dossiers/{dossier['id']}/notes",
        json={"body": "Secret fictif tres identifiable ABCXYZ", "kind": "RESERVE"},
    )
    events = client.get("/api/v1/audit").json()["items"]
    assert all("ABCXYZ" not in (event["summary"] or "") for event in events)
    note_events = [event for event in events if event["action"] == "NOTE_WRITE"]
    assert note_events and note_events[0]["fingerprint"].startswith("sha256:")


# --------------------------------------------------------------------------
# Sauvegarde et restauration (ACC-011)
# --------------------------------------------------------------------------


def test_backup_creates_verifiable_manifest(client, dossier):
    client.post(
        f"/api/v1/dossiers/{dossier['id']}/documents",
        files={"file": ("d.pdf", synthetic.make_pdf([synthetic.NATIVE_TEXT_FR]), "application/pdf")},
    )
    created = client.post("/api/v1/sauvegardes")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["includes_master_key"] is True
    assert "support chiffré" in body["warning"]

    verified = client.post(f"/api/v1/sauvegardes/{body['id']}/verification").json()
    assert verified["valid"] is True
    assert verified["mismatched"] == []


def test_corrupted_backup_is_refused_for_restore(client, tmp_path):
    created = client.post("/api/v1/sauvegardes").json()
    archive = Path(created["archive_path"])
    archive.write_bytes(archive.read_bytes()[:-200])

    response = client.post(
        "/api/v1/sauvegardes/restauration",
        json={"archive_path": str(archive), "destination": str(tmp_path / "copie")},
    )
    assert response.status_code >= 400
    assert "installation d'origine est intacte" in response.json()["error"]["message"]


def test_restore_never_overwrites_existing_data(client, tmp_path):
    created = client.post("/api/v1/sauvegardes").json()
    destination = tmp_path / "cible"
    destination.mkdir()
    (destination / "existant.txt").write_text("donnee existante", encoding="utf-8")

    response = client.post(
        "/api/v1/sauvegardes/restauration",
        json={"archive_path": created["archive_path"], "destination": str(destination)},
    )
    assert response.status_code >= 400
    assert (destination / "existant.txt").read_text(encoding="utf-8") == "donnee existante"


def test_restore_to_empty_copy_succeeds(client, tmp_path):
    created = client.post("/api/v1/sauvegardes").json()
    destination = tmp_path / "copie-vierge"
    response = client.post(
        "/api/v1/sauvegardes/restauration",
        json={"archive_path": created["archive_path"], "destination": str(destination)},
    )
    assert response.status_code == 200, response.text
    assert (destination / "base" / "commission_msi.sqlite3").exists()
    assert (destination / "cle" / "master.key").exists()
    assert "installation d'origine n'a pas été modifiée" in response.json()["message"]


def test_backup_manifest_detects_tampering(client, tmp_path):
    import zipfile

    created = client.post("/api/v1/sauvegardes").json()
    tampered = tmp_path / "trafiquee.zip"
    with zipfile.ZipFile(created["archive_path"]) as source, zipfile.ZipFile(
        tampered, "w"
    ) as target:
        for item in source.namelist():
            data = source.read(item)
            if item.endswith("master.key"):
                data = b"0" * len(data)
            target.writestr(item, data)

    result = backup_service.verify_archive(tampered)
    assert result["valid"] is False
    assert any("master.key" in path for path in result["mismatched"])


# --------------------------------------------------------------------------
# Intégrité des sources officielles (ACC-016)
# --------------------------------------------------------------------------


def test_absent_official_source_blocks_normative_rules(client):
    result = client.post("/api/v1/sources/verification").json()["items"]
    assert result
    for source in result:
        if not source["present_locally"]:
            assert "aucune règle normative dérivée" in source["message"]


def test_modified_regulation_suspends_linked_rules(client, session):
    from app.models import Regulation, Rule

    created = client.post(
        "/api/v1/reglementation",
        data={"title": "Texte fictif de reference", "reference": "FICTIF-001"},
        files={"file": ("texte.pdf", synthetic.make_pdf(["Texte officiel fictif."]), "application/pdf")},
    )
    assert created.status_code == 201
    regulation_id = created.json()["id"]

    client.post(
        f"/api/v1/reglementation/{regulation_id}/passages",
        json={"passage": "Disposition fictive citee mot pour mot.", "page_no": 1},
    )
    client.post(
        f"/api/v1/reglementation/{regulation_id}/validation",
        json={"validator": "Prof. Merzoug Mohamed"},
    )

    rule = session.query(Rule).filter_by(code="NORM-FORMAT-050").one()
    rule.regulation_id = regulation_id
    rule.active = True
    session.commit()

    regulation = session.query(Regulation).filter_by(id=regulation_id).one()
    Path(regulation.encrypted_path).write_bytes(b"contenu different apres modification")

    result = client.post(f"/api/v1/reglementation/{regulation_id}/integrite").json()
    assert result["integrity_ok"] is False
    assert result["suspended_rules"] >= 1
    assert result["status"] == "SUSPENDU"

    session.expire_all()
    assert session.query(Rule).filter_by(code="NORM-FORMAT-050").one().active is False


def test_regulation_validation_requires_paginated_passage(client):
    created = client.post(
        "/api/v1/reglementation",
        data={"title": "Texte fictif sans passage"},
        files={"file": ("t.pdf", synthetic.make_pdf(["x"]), "application/pdf")},
    )
    response = client.post(
        f"/api/v1/reglementation/{created.json()['id']}/validation",
        json={"validator": "Prof. Merzoug Mohamed"},
    )
    assert response.status_code == 422
    assert "aucun passage sourcé et paginé" in response.json()["error"]["message"]


def test_passage_without_page_is_refused(client):
    created = client.post(
        "/api/v1/reglementation",
        data={"title": "Texte fictif"},
        files={"file": ("t.pdf", synthetic.make_pdf(["x"]), "application/pdf")},
    )
    response = client.post(
        f"/api/v1/reglementation/{created.json()['id']}/passages",
        json={"passage": "Disposition sans page identifiable.", "page_no": None},
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------
# Transaction SQLite (ACC-010)
# --------------------------------------------------------------------------


def test_failed_write_keeps_previous_state(session):
    from app.core.db import session_scope
    from app.models import Dossier
    from app.services import dossier_service

    dossier_service.create_dossier(
        session, reference="MSI-TX-1", title="Titre fictif", organizer="Organisateur fictif"
    )
    before = session.query(Dossier).count()

    with pytest.raises(RuntimeError):
        with session_scope() as scoped:
            scoped.add(Dossier(reference="MSI-TX-2", title="T", organizer="O"))
            scoped.flush()
            raise RuntimeError("interruption simulee pendant l'ecriture")

    session.expire_all()
    assert session.query(Dossier).count() == before
    assert session.query(Dossier).filter_by(reference="MSI-TX-2").one_or_none() is None
