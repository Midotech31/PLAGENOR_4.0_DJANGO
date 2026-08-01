"""Fixtures de test : base isolée, clé jetable, données exclusivement fictives."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

#: Base URL loopback : l'application refuse tout hôte non local.
LOCAL_BASE_URL = "http://127.0.0.1:8731"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "data"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@pytest.fixture(autouse=True)
def isolated_environment(data_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """Chaque test dispose de sa propre base, de sa propre clé et d'aucun réseau."""
    monkeypatch.setenv("MSI_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MSI_NETWORK_DISABLED", "1")
    monkeypatch.delenv("MSI_ALLOW_REMOTE", raising=False)
    # Le worker de fond est arrêté pendant les tests : c'est le test qui décide
    # quand un travail s'exécute, sinon les assertions courraient après un fil.
    monkeypatch.setenv("MSI_WORKER_ENABLED", "0")

    from app.core import config, db, keyring
    from app.ranking import service as ranking_service
    from app.services import reference_data
    from app.web_research import egress, providers

    config.reset_settings()
    db.reset_engine()
    keyring.reset_master_key()
    reference_data.clear_cache()
    ranking_service.clear_cache()
    providers.reset_registry()
    egress.clear_egress_log()

    yield

    db.reset_engine()
    keyring.reset_master_key()
    config.reset_settings()
    egress.clear_egress_log()
    providers.reset_registry()


@pytest.fixture
def session(isolated_environment):
    """Session SQLAlchemy sur une base neuve, référentiel chargé."""
    from app.core.db import get_engine, get_session_factory
    from app.models import Base
    from app.services.seed import seed_all

    Base.metadata.create_all(bind=get_engine())
    factory = get_session_factory()
    with factory() as db_session:
        seed_all(db_session)
    with factory() as db_session:
        yield db_session


@pytest.fixture
def client(isolated_environment):
    """Client HTTP local, avec cycle de vie complet (initialisation incluse)."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(), base_url=LOCAL_BASE_URL) as test_client:
        yield test_client


@pytest.fixture
def dossier(client):
    response = client.post(
        "/api/v1/dossiers",
        json={
            "reference": "MSI-FICTIF-001",
            "title": "Colloque international fictif sur les materiaux durables",
            "organizer": "Universite Fictive de Test",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def tesseract_absent(monkeypatch: pytest.MonkeyPatch):
    """Force l'absence d'OCR local pour tester le comportement dégradé."""
    from app.services import ocr_service

    monkeypatch.setattr(ocr_service, "tesseract_command", lambda: None)


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
