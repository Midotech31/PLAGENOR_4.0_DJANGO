"""Sécurité locale : origine stricte, en-têtes, CSP, chemins sûrs.

L'application n'a aucun compte, aucun écran de connexion, aucune session
d'authentification. La protection repose sur l'isolement local : écoute sur
127.0.0.1, validation de `Host` et `Origin`, et refus des méthodes mutantes
provenant d'une origine non locale.
"""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import Settings
from app.core.errors import error_payload

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
LOCAL_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"})

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self'; "
    "media-src 'self' blob:; "
    "worker-src 'self' blob:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def is_local_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    candidate = hostname.strip().lower()
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    if candidate in LOCAL_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def split_host_header(value: str | None) -> str | None:
    """Extrait le nom d'hôte d'un en-tête `Host` (avec ou sans port)."""
    if not value:
        return None
    raw = value.strip()
    if raw.startswith("["):  # IPv6 littéral
        end = raw.find("]")
        return raw[: end + 1] if end != -1 else raw
    return raw.split(":", 1)[0]


def origin_hostname(value: str | None) -> str | None:
    if not value:
        return None
    if value.strip().lower() == "null":
        return None
    return urlsplit(value.strip()).hostname


class LocalOnlyMiddleware(BaseHTTPMiddleware):
    """Refuse toute requête dont l'hôte ou l'origine n'est pas locale."""

    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next):
        if not self.settings.allow_remote_host:
            host = split_host_header(request.headers.get("host"))
            if not is_local_hostname(host):
                return self._refuse(
                    "En-tête Host non local refusé. L'application ne doit jamais être exposée au réseau."
                )

            origin = request.headers.get("origin")
            if origin is not None and not is_local_hostname(origin_hostname(origin)):
                return self._refuse("Origine non locale refusée.")

            if request.method in MUTATING_METHODS:
                referer = request.headers.get("referer")
                if referer is not None and not is_local_hostname(origin_hostname(referer)):
                    return self._refuse("Referer non local refusé pour une méthode mutante.")

        response: Response = await call_next(request)
        self._harden(response)
        return response

    @staticmethod
    def _refuse(message: str) -> JSONResponse:
        response = JSONResponse(
            status_code=403, content=error_payload("ORIGINE_NON_LOCALE", message)
        )
        LocalOnlyMiddleware._harden(response)
        return response

    @staticmethod
    def _harden(response: Response) -> None:
        headers = response.headers
        headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), interest-cohort=()",
        )
        headers.setdefault("Cache-Control", "no-store")


def safe_filename(name: str, *, fallback: str = "document") -> str:
    """Neutralise un nom de fichier fourni par l'utilisateur.

    Supprime tout séparateur de chemin, les composants `..`, les caractères de
    contrôle et les noms réservés Windows.
    """
    candidate = unicodedata.normalize("NFKC", name or "")
    candidate = candidate.replace("\\", "/").split("/")[-1]
    candidate = candidate.replace("\x00", "")
    candidate = _SAFE_NAME_RE.sub("_", candidate).strip("._ ")
    if not candidate or set(candidate) <= {"."}:
        return fallback
    stem = candidate.split(".", 1)[0].upper()
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {
        f"LPT{i}" for i in range(1, 10)
    }
    if stem in reserved:
        candidate = f"_{candidate}"
    return candidate[:180]


def resolve_within(base: Path, *parts: str) -> Path:
    """Résout un chemin en garantissant qu'il reste sous `base`.

    Protège contre la traversée de répertoire (`../`, chemins absolus, liens).
    """
    base_resolved = base.resolve()
    candidate = base_resolved
    for part in parts:
        candidate = candidate / safe_filename(part)
    resolved = candidate.resolve()
    if resolved != base_resolved and base_resolved not in resolved.parents:
        raise ValueError("Chemin refusé : sortie du répertoire autorisé.")
    return resolved
