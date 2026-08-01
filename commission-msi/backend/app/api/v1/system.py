"""Santé, disponibilité et diagnostic local.

Aucune route `/setup`, `/login` ou `/logout` n'existe : l'application s'ouvre
directement sur le tableau de bord.
"""

from __future__ import annotations

import socket

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import APP_NAME, SIGNATURE, SIGNATURE_FR, get_settings
from app.core.db import get_db
from app.core.vocabulary import (
    DISPLAYED_LIMITS,
    Conclusion,
    ControlStatus,
    DossierStatus,
    FindingStatus,
    Gate,
    InformationStatus,
    MarocRelation,
    PieceStatus,
    Priority,
)
from app.models import Dossier, Rule
from app.services import ocr_service

router = APIRouter(tags=["système"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "application": APP_NAME,
        "version": settings.version,
        "designed_by": SIGNATURE,
        "conçu_par": SIGNATURE_FR,
        "authentication": "aucune — application locale sans compte ni écran de connexion",
    }


@router.get("/readiness")
def readiness(session: Session = Depends(get_db)) -> dict:
    """Prêt = base accessible et référentiel chargé. Le lanceur attend cet état."""
    checks: dict[str, bool] = {}
    try:
        session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:  # noqa: BLE001
        checks["database"] = False
    try:
        checks["referential"] = session.scalar(select(Rule).limit(1)) is not None
    except Exception:  # noqa: BLE001
        checks["referential"] = False
    settings = get_settings()
    checks["data_directory"] = settings.data_dir.exists()
    checks["master_key"] = settings.key_path.exists()
    ready = all(checks.values())
    return {
        "ready": ready,
        "checks": checks,
        "message": (
            "Serveur prêt : le tableau de bord peut s'ouvrir."
            if ready
            else "Serveur non prêt. Attendez la fin de l'initialisation avant d'ouvrir le navigateur."
        ),
    }


@router.get("/diagnostic")
def diagnostic(session: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    dossiers = len(list(session.scalars(select(Dossier)).all()))
    return {
        "application": APP_NAME,
        "version": settings.version,
        "designed_by": SIGNATURE,
        "bind_host": settings.host,
        "bind_port": settings.port,
        "listens_locally_only": settings.host in {"127.0.0.1", "localhost", "::1"}
        and not settings.allow_remote_host,
        "network_policy": "Aucune ressource Internet, aucun CDN, aucune télémétrie, aucun appel d'API externe.",
        "data_directory": str(settings.data_dir),
        "database": str(settings.db_path),
        "master_key_present": settings.key_path.exists(),
        "dossiers": dossiers,
        "ocr": ocr_service.diagnostic(),
        "max_upload_mb": settings.max_upload_mb,
        "security_notes": [
            "Ne perdez jamais master.key : sans elle, les données chiffrées sont définitivement illisibles.",
            "Activez le chiffrement complet du disque (BitLocker) : le chiffrement applicatif ne le remplace pas.",
            "N'exposez jamais cette application au réseau : elle n'a ni compte ni mot de passe.",
        ],
        "limits": list(DISPLAYED_LIMITS),
    }


@router.get("/vocabulary")
def vocabulary() -> dict:
    """Vocabulaire contrôlé exposé à l'interface (aucune valeur libre)."""
    return {
        "dossier_status": [item.value for item in DossierStatus],
        "information_status": [item.value for item in InformationStatus],
        "piece_status": [item.value for item in PieceStatus],
        "control_status": [item.value for item in ControlStatus],
        "finding_status": [item.value for item in FindingStatus],
        "priority": [item.value for item in Priority],
        "conclusions": [item.value for item in Conclusion],
        "maroc_relations": [item.value for item in MarocRelation],
        "gates": [item.value for item in Gate],
        "forbidden_automatic_outputs": ["ACCEPTE", "REJETE", "INTERDIT", "NOTE_AUTOMATIQUE", "AVIS_DEFINITIF"],
    }


@router.get("/limits")
def limits() -> dict:
    return {"limits": list(DISPLAYED_LIMITS), "designed_by": SIGNATURE}


@router.get("/mode-analyse")
def analysis_mode() -> dict:
    """Mode d'intelligence artificielle et garanties de confidentialité (§5).

    La clé API n'est jamais renvoyée, ni même son empreinte : seule sa présence
    ou son absence est indiquée à travers la liste des éléments manquants.
    """
    from app.services import ai_provider

    state = ai_provider.status()
    state["guarantees"] = [
        "Le PDF original reste chiffré en local et n'est jamais transmis.",
        "Les pièces d'identité et les numéros de passeport ne sont jamais transmis au modèle "
        "ni utilisés dans une recherche Web.",
        "La recherche publique ne porte que sur des identités professionnelles et des "
        "informations déjà publiques.",
        "Le raisonnement privé du modèle n'est ni conservé ni affiché.",
        "Chaque transmission externe est inscrite à l'audit avec le type de données, jamais "
        "avec le contenu sensible en clair.",
        "Le choix du statut réglementaire, de la note et de l'avis reste déterministe et local.",
    ]
    return state


def port_is_free(host: str, port: int) -> bool:
    """Utilisé par le lanceur : le port doit être ouvert avant le navigateur."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True
