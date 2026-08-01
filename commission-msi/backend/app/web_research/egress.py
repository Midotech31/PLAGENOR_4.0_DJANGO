"""Politique de sortie réseau : liste blanche, TLS obligatoire, coupure immédiate.

Toute sortie réseau de l'application passe par ce module. Le cœur documentaire
(import, OCR, saisie, rapports) n'y fait jamais appel : il fonctionne hors ligne.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit

from app.core.errors import AppError

#: Domaines autorisés par défaut : uniquement des sources publiques
#: institutionnelles, scientifiques ou officielles. Modifiable via
#: MSI_ALLOWED_DOMAINS (liste séparée par des virgules).
DEFAULT_ALLOWED_DOMAINS: tuple[str, ...] = (
    "api.crossref.org",
    "api.openalex.org",
    "pub.orcid.org",
    "api.ror.org",
    "doaj.org",
    "api.datacite.org",
)

#: Fichier local listant les domaines refusés en plus de la liste blanche.
ENV_ALLOWED = "MSI_ALLOWED_DOMAINS"
ENV_KILL_SWITCH = "MSI_NETWORK_DISABLED"


class EgressRefused(AppError):
    """Sortie réseau refusée par la politique locale."""

    code = "SORTIE_RESEAU_REFUSEE"
    status_code = 403


@dataclass
class EgressLogEntry:
    domain: str
    url: str
    allowed: bool
    reason: str
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EgressPolicy:
    """Politique de sortie effective, rechargée à chaque vérification."""

    allowed_domains: tuple[str, ...]
    disabled: bool

    @classmethod
    def current(cls) -> "EgressPolicy":
        raw = os.environ.get(ENV_ALLOWED, "")
        domains = tuple(
            part.strip().lower() for part in raw.split(",") if part.strip()
        ) or DEFAULT_ALLOWED_DOMAINS
        disabled = os.environ.get(ENV_KILL_SWITCH, "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "oui",
        }
        return cls(allowed_domains=domains, disabled=disabled)


#: Journal en mémoire des domaines appelés (repris dans l'audit persistant).
_egress_log: list[EgressLogEntry] = []


def egress_log() -> list[EgressLogEntry]:
    return list(_egress_log)


def clear_egress_log() -> None:
    _egress_log.clear()


def domain_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def is_allowed(url: str, policy: EgressPolicy | None = None) -> tuple[bool, str]:
    """Vérifie qu'une URL respecte la politique de sortie, sans l'appeler."""
    policy = policy or EgressPolicy.current()
    if policy.disabled:
        return False, "Accès externes coupés par l'interrupteur local (MSI_NETWORK_DISABLED)."

    parts = urlsplit(url)
    if parts.scheme != "https":
        return False, "TLS obligatoire : seules les URL https sont autorisées."

    host = (parts.hostname or "").lower()
    if not host:
        return False, "URL sans nom d'hôte."
    for allowed in policy.allowed_domains:
        if host == allowed or host.endswith("." + allowed):
            return True, f"Domaine autorisé par la liste blanche ({allowed})."
    return False, (
        f"Domaine « {host} » absent de la liste blanche. Ajoutez-le explicitement dans "
        f"{ENV_ALLOWED} après vérification de ses conditions d'utilisation."
    )


def authorize(url: str, policy: EgressPolicy | None = None) -> str:
    """Autorise une sortie réseau ou lève :class:`EgressRefused`.

    Chaque tentative — autorisée ou refusée — est journalisée.
    """
    allowed, reason = is_allowed(url, policy)
    _egress_log.append(EgressLogEntry(domain=domain_of(url), url=url, allowed=allowed, reason=reason))
    if not allowed:
        raise EgressRefused(reason)
    return reason


def policy_state() -> dict:
    policy = EgressPolicy.current()
    return {
        "network_disabled": policy.disabled,
        "allowed_domains": list(policy.allowed_domains),
        "tls_required": True,
        "inbound_listen": "127.0.0.1 uniquement",
        "kill_switch_env": ENV_KILL_SWITCH,
        "allowlist_env": ENV_ALLOWED,
        "recent_calls": [
            {"domain": entry.domain, "allowed": entry.allowed, "reason": entry.reason, "at": entry.at}
            for entry in _egress_log[-50:]
        ],
        "notice": (
            "Seul le module de recherche contrôlée émet des appels sortants. Aucun PDF, aucune "
            "pièce, aucun document d'identité et aucune note interne ne quitte jamais le poste."
        ),
    }
