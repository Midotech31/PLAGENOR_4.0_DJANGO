"""Fournisseurs de recherche publique, configurables et désactivables un par un.

Les clés API sont lues uniquement dans les variables d'environnement locales ou
le coffre local. Elles ne sont jamais écrites dans le code, les journaux, les
réponses de l'API ou les sauvegardes.
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import quote

from app.core.vocabulary import SourceTier
from app.web_research import egress

DEFAULT_TIMEOUT = 15


@dataclass
class SearchResult:
    url: str
    title: str
    publisher: str | None
    published_on: str | None
    snippet: str
    tier: str
    language: str | None = None
    consulted_at: datetime | None = None


class SearchProvider(Protocol):
    name: str
    tier: str

    def is_configured(self) -> bool: ...

    def is_enabled(self) -> bool: ...

    def search(self, query: str, *, limit: int = 5) -> list[SearchResult]: ...


def _disabled_env(name: str) -> bool:
    return os.environ.get(f"MSI_PROVIDER_{name.upper()}_DISABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "oui",
    }


@dataclass
class HttpJsonProvider:
    """Fournisseur public interrogé en HTTPS et renvoyant du JSON.

    Chaque appel est soumis à la politique de sortie (liste blanche + TLS).
    """

    name: str
    endpoint_template: str
    tier: str
    result_path: tuple[str, ...]
    field_map: dict[str, str]
    api_key_env: str | None = None
    requires_key: bool = False

    def is_configured(self) -> bool:
        if not self.requires_key:
            return True
        return bool(self.api_key_env and os.environ.get(self.api_key_env, "").strip())

    def is_enabled(self) -> bool:
        return self.is_configured() and not _disabled_env(self.name)

    def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        url = self.endpoint_template.format(query=quote(query), limit=limit)
        egress.authorize(url)

        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        if self.requires_key and self.api_key_env:
            key = os.environ.get(self.api_key_env, "").strip()
            if key:
                request.add_header("Authorization", f"Bearer {key}")

        context = ssl.create_default_context()
        with urllib.request.urlopen(  # noqa: S310 - schéma https imposé par egress.authorize
            request, timeout=DEFAULT_TIMEOUT, context=context
        ) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))

        node = payload
        for step in self.result_path:
            node = node.get(step, []) if isinstance(node, dict) else []
        if not isinstance(node, list):
            return []

        now = datetime.now(timezone.utc)
        results: list[SearchResult] = []
        for item in node[:limit]:
            if not isinstance(item, dict):
                continue
            results.append(
                SearchResult(
                    url=str(_dig(item, self.field_map.get("url")) or url),
                    title=str(_dig(item, self.field_map.get("title")) or "Sans titre"),
                    publisher=_optional_str(_dig(item, self.field_map.get("publisher"))),
                    published_on=_optional_str(_dig(item, self.field_map.get("published_on"))),
                    snippet=str(_dig(item, self.field_map.get("snippet")) or "")[:600],
                    tier=self.tier,
                    consulted_at=now,
                )
            )
        return results


def _dig(item: dict, path: str | None):
    if not path:
        return None
    node = item
    for step in path.split("."):
        if isinstance(node, list):
            node = node[0] if node else None
        if not isinstance(node, dict):
            return None
        node = node.get(step)
    if isinstance(node, list):
        return node[0] if node else None
    return node


def _optional_str(value) -> str | None:
    return str(value) if value not in (None, "") else None


#: Fournisseurs publics par défaut, tous sans clé API et sans donnée personnelle.
DEFAULT_PROVIDERS: tuple[HttpJsonProvider, ...] = (
    HttpJsonProvider(
        name="openalex",
        endpoint_template="https://api.openalex.org/works?search={query}&per-page={limit}",
        tier=SourceTier.T3_PUBLICATION_SCIENTIFIQUE,
        result_path=("results",),
        field_map={
            "url": "doi",
            "title": "display_name",
            "publisher": "host_venue.display_name",
            "published_on": "publication_date",
            "snippet": "display_name",
        },
    ),
    HttpJsonProvider(
        name="crossref",
        endpoint_template="https://api.crossref.org/works?query={query}&rows={limit}",
        tier=SourceTier.T3_PUBLICATION_SCIENTIFIQUE,
        result_path=("message", "items"),
        field_map={
            "url": "URL",
            "title": "title",
            "publisher": "publisher",
            "published_on": "created.date-time",
            "snippet": "title",
        },
    ),
    HttpJsonProvider(
        name="ror",
        endpoint_template="https://api.ror.org/organizations?query={query}",
        tier=SourceTier.T2_INSTITUTION_ACADEMIQUE,
        result_path=("items",),
        field_map={
            "url": "links",
            "title": "name",
            "publisher": "country.country_name",
            "snippet": "name",
        },
    ),
    HttpJsonProvider(
        name="orcid",
        endpoint_template="https://pub.orcid.org/v3.0/expanded-search/?q={query}&rows={limit}",
        tier=SourceTier.T2_INSTITUTION_ACADEMIQUE,
        result_path=("expanded-result",),
        field_map={
            "url": "orcid-id",
            "title": "credit-name",
            "publisher": "institution-name",
            "snippet": "credit-name",
        },
    ),
)

_registry: dict[str, SearchProvider] = {provider.name: provider for provider in DEFAULT_PROVIDERS}


def register(provider: SearchProvider) -> None:
    """Enregistre un fournisseur (utilisé par les tests et les déploiements locaux)."""
    _registry[provider.name] = provider


def unregister(name: str) -> None:
    _registry.pop(name, None)


def reset_registry() -> None:
    _registry.clear()
    for provider in DEFAULT_PROVIDERS:
        _registry[provider.name] = provider


def get(name: str) -> SearchProvider | None:
    return _registry.get(name)


def enabled_providers() -> list[SearchProvider]:
    return [provider for provider in _registry.values() if provider.is_enabled()]


def provider_states() -> list[dict]:
    return [
        {
            "name": provider.name,
            "tier": provider.tier,
            "configured": provider.is_configured(),
            "enabled": provider.is_enabled(),
            "disable_env": f"MSI_PROVIDER_{provider.name.upper()}_DISABLED",
        }
        for provider in _registry.values()
    ]


def check_connectivity(timeout: int = 5) -> dict:
    """Vérifie la connectivité sortante sans transmettre la moindre donnée du dossier."""
    policy = egress.EgressPolicy.current()
    if policy.disabled:
        return {
            "online": False,
            "reason": "Accès externes coupés localement (interrupteur MSI_NETWORK_DISABLED).",
            "checked_at": datetime.now(timezone.utc),
        }
    for domain in policy.allowed_domains:
        try:
            with socket.create_connection((domain, 443), timeout=timeout):
                return {
                    "online": True,
                    "reason": f"Connexion TLS possible vers {domain}.",
                    "checked_at": datetime.now(timezone.utc),
                }
        except OSError:
            continue
    return {
        "online": False,
        "reason": "Aucun domaine de la liste blanche n'est joignable.",
        "checked_at": datetime.now(timezone.utc),
    }


def safe_search(provider: SearchProvider, query: str, *, limit: int = 5) -> tuple[list[SearchResult], str | None]:
    """Exécute une recherche en convertissant toute panne en échec explicite."""
    try:
        return provider.search(query, limit=limit), None
    except egress.EgressRefused as exc:
        return [], f"Sortie refusée : {exc.message}"
    except urllib.error.HTTPError as exc:
        return [], f"Fournisseur {provider.name} : réponse HTTP {exc.code}."
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        return [], f"Fournisseur {provider.name} injoignable ou délai dépassé ({exc.__class__.__name__})."
    except (json.JSONDecodeError, ValueError, KeyError):
        return [], f"Fournisseur {provider.name} : réponse incomplète ou illisible."
