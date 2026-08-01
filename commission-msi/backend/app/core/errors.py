"""Erreurs applicatives et réponses d'erreur sans fuite technique."""

from __future__ import annotations

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.core.config import CONTRADICTION_MESSAGE, UNCERTAIN_MESSAGE


class AppError(Exception):
    """Erreur métier destinée à l'utilisateur, sans détail technique."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "ERREUR"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationRefused(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "VALIDATION_REFUSEE"


class ProvenanceRequired(AppError):
    """Un fait ne peut pas être enregistré sans document, page ou passage."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "PROVENANCE_REQUISE"


class GateBlocked(AppError):
    """Une porte de validation (G0..G7) n'est pas satisfaite."""

    status_code = status.HTTP_409_CONFLICT
    code = "PORTE_NON_SATISFAITE"


class ContradictionDetected(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONTRADICTION_A_ARBITRER"

    def __init__(self, message: str | None = None, *, details: dict | None = None) -> None:
        super().__init__(message or CONTRADICTION_MESSAGE, details=details)


class UnreliableContent(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "CONTENU_NON_FIABLE"

    def __init__(self, message: str | None = None, *, details: dict | None = None) -> None:
        super().__init__(message or UNCERTAIN_MESSAGE, details=details)


class NotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "INTROUVABLE"


class LocalOnlyRefused(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "ORIGINE_NON_LOCALE"


def error_payload(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(exc.code, exc.message, exc.details),
    )


async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Requête refusée."
    return JSONResponse(status_code=exc.status_code, content=error_payload("HTTP", detail))


#: Traduction des contraintes Pydantic en phrases utilisables par l'évaluateur.
#: Sans elles, l'interface n'affiche qu'un « 422 » qui n'apprend rien.
def _explain_constraint(error: dict) -> str:
    kind = error.get("type", "")
    context = error.get("ctx") or {}
    field = ".".join(str(part) for part in error.get("loc", ()) if part != "body") or "champ"

    if kind in {"string_too_short", "too_short"}:
        minimum = context.get("min_length", context.get("min_length", 1))
        return (
            f"« {field} » : une motivation d'au moins {minimum} caractères est obligatoire. "
            "Toute qualification humaine doit être justifiée."
        )
    if kind in {"string_too_long", "too_long"}:
        return f"« {field} » : le texte dépasse la longueur maximale autorisée."
    if kind == "missing":
        return f"« {field} » est obligatoire et n'a pas été fourni."
    if kind == "string_pattern_mismatch":
        return f"« {field} » n'a pas une valeur acceptée."
    if kind in {"greater_than_equal", "less_than_equal"}:
        return (
            f"« {field} » doit rester entre {context.get('ge', 0)} et "
            f"{context.get('le', '—')}."
        )
    if kind == "enum":
        expected = context.get("expected", "")
        return f"« {field} » doit être choisi parmi : {expected}."
    return f"« {field} » : {error.get('msg', 'valeur refusée')}."


async def validation_error_handler(_request: Request, exc) -> JSONResponse:
    """Transforme une erreur de schéma en message actionnable, pas en code brut."""
    raw = exc.errors() if hasattr(exc, "errors") else []
    reasons = [_explain_constraint(item) for item in raw]
    message = " ".join(reasons) or "La requête a été refusée : une valeur ne respecte pas le format attendu."
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_payload("VALIDATION_REFUSEE", message, {"champs": len(raw)}),
    )


async def unexpected_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    """Aucune trace technique n'est renvoyée à l'interface."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_payload(
            "ERREUR_INTERNE",
            "L'opération a été interrompue et l'état précédent a été conservé. "
            "Consultez le journal technique local.",
        ),
    )
