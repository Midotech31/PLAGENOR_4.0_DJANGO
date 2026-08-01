"""Point d'entrée FastAPI.

Application locale d'examen des manifestations scientifiques internationales.
Designed by Prof. Merzoug Mohamed — Conçu par le Professeur Merzoug Mohamed.

Aucune route `/setup`, `/login` ou `/logout`. Le tableau de bord s'ouvre
directement. Le serveur écoute uniquement sur 127.0.0.1.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import dossiers, referentials, system, web_research
from app.core.config import APP_NAME, SIGNATURE, SIGNATURE_FR, get_settings
from app.core.db import get_engine, session_scope
from app.core.errors import (
    AppError,
    app_error_handler,
    http_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from app.core.keyring import get_master_key
from app.core.security import LocalOnlyMiddleware
from app.models import Base

logger = logging.getLogger("commission_msi")

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def initialize_storage() -> None:
    """Crée la base et le référentiel si nécessaire, sans jamais réinitialiser."""
    settings = get_settings()
    settings.ensure_directories()
    get_master_key()
    Base.metadata.create_all(bind=get_engine())
    from app.services.seed import seed_all

    with session_scope() as session:
        seed_all(session)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.core import audit

    initialize_storage()
    with session_scope() as session:
        audit.record(
            session,
            audit.AuditAction.APP_START,
            f"Démarrage local de {APP_NAME} version {get_settings().version}.",
        )
    logger.info("%s prêt sur http://%s:%s", APP_NAME, get_settings().host, get_settings().port)

    # Le worker d'analyse tourne hors du fil des requêtes HTTP : fermer le
    # navigateur ou perdre une requête n'interrompt jamais un traitement.
    worker: tuple | None = None
    if get_settings().worker_enabled:
        from app.services import job_service

        worker = job_service.start_background_worker()
        logger.info("Worker d'analyse démarré (travaux durables en base).")

    yield

    if worker is not None:
        _thread, stop = worker
        stop.set()
    with session_scope() as session:
        audit.record(session, audit.AuditAction.APP_STOP, "Arrêt de l'application.")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=APP_NAME,
        version=settings.version,
        description=(
            "Application locale d'aide à l'examen des demandes d'organisation de manifestations "
            "scientifiques internationales. Elle extrait, vérifie, classe, compare, signale et "
            "prépare ; l'évaluateur humain contrôle, interprète, apprécie et décide.\n\n"
            f"{SIGNATURE} — {SIGNATURE_FR}."
        ),
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(LocalOnlyMiddleware, settings=settings)
    from fastapi.exceptions import RequestValidationError

    app.add_exception_handler(AppError, app_error_handler)
    # Sans ce gestionnaire, une contrainte de schéma n'arrive à l'interface que
    # sous la forme « Requête refusée (422) », qui n'aide personne.
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)

    api = APIRouter(prefix="/api/v1")
    api.include_router(system.router)
    api.include_router(dossiers.router)
    api.include_router(web_research.router)
    api.include_router(referentials.router)
    app.include_router(api)
    _register_api_fallback(app)

    _mount_frontend(app)
    return app


def _register_api_fallback(app: FastAPI) -> None:
    """Toute route d'API inconnue répond 404, quelle que soit la méthode.

    Garantit notamment qu'aucune route `/setup`, `/login` ou `/logout`
    n'existe ni ne semble exister sous une autre méthode HTTP.
    """

    @app.api_route(
        "/api/{unknown_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        include_in_schema=False,
        response_model=None,
    )
    async def unknown_api_route(unknown_path: str) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "INTROUVABLE",
                    "message": "Route d'API inconnue.",
                    "details": {"path": f"/api/{unknown_path}"},
                }
            },
        )


def _mount_frontend(app: FastAPI) -> None:
    """Sert le frontend compilé — aucune ressource distante n'est chargée."""
    index = FRONTEND_DIST / "index.html"
    if (FRONTEND_DIST / "assets").is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(FRONTEND_DIST / "assets")),
            name="assets",
        )

    @app.get("/", include_in_schema=False, response_model=None)
    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def serve_spa(full_path: str = ""):
        if full_path.startswith("api/"):
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "INTROUVABLE", "message": "Route d'API inconnue."}},
            )
        if index.exists():
            return FileResponse(index)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "INTERFACE_ABSENTE",
                    "message": (
                        "L'interface compilée est absente. Exécutez « npm run build » dans "
                        "frontend/, ou utilisez install_windows.bat."
                    ),
                }
            },
        )


app = create_app()
