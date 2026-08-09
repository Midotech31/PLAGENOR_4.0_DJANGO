"""Abstraction `AIProvider` : mode `LOCAL_ONLY` ou `HYBRID_STRICT` (§5).

Ce que le mode hybride change et ce qu'il ne change pas :

* **jamais transmis** : le PDF original, les pièces d'identité, les numéros de
  passeport. Le garde-fou est appliqué ici, dans le code, et pas seulement dans
  la configuration — une variable d'environnement ne peut pas l'ouvrir ;
* **transmis** : uniquement les blocs de texte explicitement autorisés, avec
  leurs identifiants de preuve ;
* **jamais conservé** : le raisonnement privé du modèle. L'audit enregistre le
  modèle, la durée, les catégories de données et des empreintes — jamais le
  contenu en clair.

Le chemin de décision reste déterministe : le modèle ne choisit ni statut, ni
note, ni avis. Il sert à la lecture sémantique et à la recherche publique.

Aucun basculement silencieux vers un modèle plus faible : si le modèle demandé
est indisponible, l'appel échoue avec `MODEL_UNAVAILABLE` et le travail reste
reprenable après correction.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AiCall
from app.models.base import new_id

LOCAL_ONLY = "LOCAL_ONLY"
#: Modèle de langage installé **sur le poste**. Rien ne sort — c'est la garantie
#: de souveraineté du mode local, avec la lecture sémantique en plus.
LOCAL_MODEL = "LOCAL_MODEL"
HYBRID_STRICT = "HYBRID_STRICT"
MODES = (LOCAL_ONLY, LOCAL_MODEL, HYBRID_STRICT)

#: Modes capables de lecture sémantique. Les deux valent pour l'étape de
#: lecture ; ils diffèrent par ce qui quitte le poste, pas par ce qu'ils font.
READING_MODES = (LOCAL_MODEL, HYBRID_STRICT)

PROMPT_VERSION = "2026.08.1"

#: Message affiché quand le mode local est actif.
LOCAL_ONLY_NOTICE = (
    "Mode LOCAL_ONLY : aucune lecture sémantique. Seules les informations écrites sous la "
    "forme « Libellé : valeur » sont extraites ; celles rédigées en prose ou en tableau "
    "resteront signalées « non vérifiable ». Le nom de ce mode ne désigne pas le modèle "
    "local : pour faire lire le dossier sans que rien ne quitte le poste, installez un "
    "modèle local (mode LOCAL_MODEL)."
)

#: Motifs de données interdites de transmission, quelle que soit la configuration.
PASSPORT_PATTERNS = (
    re.compile(r"\b(?:passeport|passport|جواز)\b[^\n]{0,40}?[A-Z0-9]{6,12}", re.IGNORECASE),
    re.compile(r"\bn[°ºo]?\s*(?:de\s+)?passeport\b[^\n]{0,30}", re.IGNORECASE),
    re.compile(r"\b[A-Z]{1,2}\d{6,9}\b"),  # format courant de numéro de document
)

REDACTED = "[donnée restreinte retirée avant transmission]"


class AiError(RuntimeError):
    """Erreur d'appel au modèle, avec un code exploitable par le worker."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ExternalAiNotConfigured(AiError):
    def __init__(self, reason: str) -> None:
        super().__init__("EXTERNAL_AI_NOT_CONFIGURED", reason)


class ModelUnavailable(AiError):
    def __init__(self, model_id: str) -> None:
        super().__init__(
            "MODEL_UNAVAILABLE",
            f"Le modèle « {model_id} » n'est pas disponible pour ce compte. Aucun basculement "
            "silencieux vers un modèle moins performant n'est effectué : corrigez la "
            "configuration, puis reprenez le travail.",
        )


class RestrictedContentRefused(AiError):
    def __init__(self, what: str) -> None:
        super().__init__(
            "RESTRICTED_CONTENT_REFUSED",
            f"Transmission refusée : {what}. Les pièces d'identité, les numéros de passeport "
            "et le PDF original ne quittent jamais le poste.",
        )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def redact(text: str) -> tuple[str, list[str]]:
    """Retire les données restreintes avant toute transmission externe.

    Retourne le texte expurgé et la liste des catégories retirées, pour que
    l'audit puisse dire *ce qui* a été protégé sans jamais le recopier.
    """
    redacted = text
    categories: list[str] = []
    for pattern in PASSPORT_PATTERNS:
        redacted, count = pattern.subn(REDACTED, redacted)
        if count and "PIECE_IDENTITE" not in categories:
            categories.append("PIECE_IDENTITE")
    return redacted, categories


@dataclass
class AiRequest:
    """Un appel au modèle : des blocs autorisés et leurs identifiants de preuve."""

    role: str
    instruction: str
    blocks: list[dict] = field(default_factory=list)
    json_schema: dict | None = None

    def payload(self) -> str:
        return json.dumps(
            {"instruction": self.instruction, "blocks": self.blocks}, ensure_ascii=False,
            sort_keys=True,
        )


@dataclass
class AiResponse:
    role: str
    model_id: str
    content: dict
    status: str
    duration_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    data_categories: list[str] = field(default_factory=list)


class AIProvider:
    """Interface commune aux deux modes."""

    mode: str = LOCAL_ONLY

    def available(self) -> bool:
        raise NotImplementedError

    def describe(self) -> dict:
        raise NotImplementedError

    def complete(self, request: AiRequest) -> AiResponse:
        raise NotImplementedError


class LocalOnlyProvider(AIProvider):
    """Aucune donnée ne quitte le poste ; l'analyse reste déterministe."""

    mode = LOCAL_ONLY

    def available(self) -> bool:
        return True

    def describe(self) -> dict:
        return {
            "mode": LOCAL_ONLY,
            "available": True,
            "model_id": None,
            "notice": LOCAL_ONLY_NOTICE,
            "external_transmission": False,
        }

    def complete(self, request: AiRequest) -> AiResponse:
        raise AiError(
            "LOCAL_ONLY_NO_MODEL",
            "Aucun appel externe n'est possible en mode LOCAL_ONLY. Les constats produits "
            "reposent uniquement sur les moteurs déterministes locaux.",
        )


class LocalModelProvider(AIProvider):
    """Lecture sémantique par un modèle installé sur le poste.

    Aucune expurgation n'est nécessaire et aucune n'est faite : rien ne quitte
    la machine, donc il n'y a rien à protéger d'un tiers. Les pages classées
    `RESTREINT` restent néanmoins écartées à la source par l'appelant — ce qui
    ne doit pas être lu par un modèle ne doit pas l'être non plus par un modèle
    local, la classification exprime une règle de traitement, pas seulement une
    règle de transmission.
    """

    mode = LOCAL_MODEL

    def __init__(self, *, client=None) -> None:
        self._client = client

    def _settings(self):
        return get_settings()

    def available(self) -> bool:
        return bool(self._settings().local_model_name)

    def describe(self) -> dict:
        settings = self._settings()
        missing = []
        if not settings.local_model_name:
            missing.append("MSI_LOCAL_MODEL (identifiant du modèle installé)")
        return {
            "mode": LOCAL_MODEL,
            "available": not missing,
            "model_id": settings.local_model_name or None,
            "missing": missing,
            "server_url": settings.local_model_url,
            "context_tokens": settings.local_model_context,
            "notice": "Mode LOCAL_MODEL : la lecture sémantique est faite par un modèle "
            "installé sur ce poste. Rien ne quitte la machine — ni le PDF, ni les pièces "
            "d'identité, ni le texte des pages. Un modèle local lit moins bien qu'un "
            "modèle de service : il proposera moins de valeurs, jamais des valeurs moins "
            "vérifiées.",
            "external_transmission": False,
        }

    def complete(self, request: AiRequest) -> AiResponse:
        settings = self._settings()
        if not self.available():
            raise ExternalAiNotConfigured(
                "aucun modèle local n'est configuré : "
                + ", ".join(self.describe()["missing"])
                + "."
            )
        if self._client is None:
            from app.services.local_model_client import LocalModelClient

            self._client = LocalModelClient()

        started = time.monotonic()
        try:
            content = self._client.complete(model_id=settings.local_model_name, request=request)
        except LookupError as exc:
            raise ModelUnavailable(settings.local_model_name) from exc
        except AiError:
            raise
        except Exception as exc:  # noqa: BLE001 - toute panne devient un code exploitable
            raise AiError(
                "AI_CALL_FAILED",
                f"L'appel au modèle local n'a pas abouti : {exc}. Le travail reste "
                "reprenable une fois la cause corrigée.",
            ) from exc
        duration = int((time.monotonic() - started) * 1000)

        return AiResponse(
            role=request.role,
            model_id=settings.local_model_name,
            content=content,
            status="OK",
            duration_ms=duration,
            # Aucune donnée n'est sortie : la catégorie dit ce qui a été lu, pas
            # ce qui a été transmis.
            data_categories=["EXTRAIT_TEXTE_LOCAL"],
        )


class HybridStrictProvider(AIProvider):
    """Appels externes limités aux blocs autorisés, jamais aux pièces d'identité."""

    mode = HYBRID_STRICT

    def __init__(self, *, client=None) -> None:
        self._client = client

    def _settings(self):
        return get_settings()

    def available(self) -> bool:
        settings = self._settings()
        return bool(
            settings.allow_external_ai
            and settings.anthropic_api_key
            and settings.anthropic_model_analysis
            and settings.privacy_acknowledged
        )

    def describe(self) -> dict:
        settings = self._settings()
        missing = []
        if not settings.allow_external_ai:
            missing.append("ALLOW_EXTERNAL_AI")
        if not settings.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        if not settings.anthropic_model_analysis:
            missing.append("ANTHROPIC_MODEL_ANALYSIS")
        if not settings.privacy_acknowledged:
            missing.append("validation de la configuration de confidentialité")
        return {
            "mode": HYBRID_STRICT,
            "available": not missing,
            # L'identifiant du modèle est journalisé ; la clé ne l'est jamais.
            "model_id": settings.anthropic_model_analysis or None,
            "audit_model_id": settings.anthropic_model_audit or None,
            "missing": missing,
            "notice": "Mode HYBRID_STRICT : seuls les extraits autorisés sont transmis à "
            "l'extérieur. Le PDF original, les pièces d'identité et les numéros de passeport "
            "restent chiffrés en local et ne sont jamais transmis.",
            "external_transmission": not missing,
        }

    def _model_for(self, role: str) -> str:
        settings = self._settings()
        model = (
            settings.anthropic_model_audit
            if role.upper().startswith("AUDIT") and settings.anthropic_model_audit
            else settings.anthropic_model_analysis
        )
        if not model:
            raise ExternalAiNotConfigured(
                "aucun identifiant de modèle n'est configuré (ANTHROPIC_MODEL_ANALYSIS)."
            )
        return model

    def complete(self, request: AiRequest) -> AiResponse:
        settings = self._settings()
        if not self.available():
            raise ExternalAiNotConfigured(
                "le mode HYBRID_STRICT n'est pas complètement configuré : "
                + ", ".join(self.describe()["missing"])
                + "."
            )
        if settings.send_identity_documents:
            # La configuration ne peut pas ouvrir cette porte : elle est fermée ici.
            raise RestrictedContentRefused(
                "la transmission des pièces d'identité a été demandée par configuration"
            )

        redacted_blocks: list[dict] = []
        categories: list[str] = ["EXTRAIT_TEXTE"]
        for block in request.blocks:
            if block.get("sensitivity") == "RESTREINT":
                raise RestrictedContentRefused(
                    f"le bloc « {block.get('evidence_id', '—')} » est classé restreint"
                )
            # L'expurgation lit du texte : elle ne peut rien voir dans une image.
            # Un bloc image n'est donc transmis que si sa classification a été
            # posée explicitement — l'absence de classification vaut refus.
            if str(block.get("kind", "")).startswith("image/"):
                if "sensitivity" not in block:
                    raise RestrictedContentRefused(
                        "un bloc image sans classification de sensibilité a été soumis ; "
                        "aucune expurgation n'est possible sur une image"
                    )
                categories.append("IMAGE_PAGE")
                redacted_blocks.append(block)
                continue
            text, removed = redact(str(block.get("text", "")))
            redacted_blocks.append({**block, "text": text})
            for category in removed:
                if category not in categories:
                    categories.append(category)

        model_id = self._model_for(request.role)
        payload = AiRequest(
            role=request.role,
            instruction=request.instruction,
            blocks=redacted_blocks,
            json_schema=request.json_schema,
        )

        started = time.monotonic()
        try:
            content = self._call(model_id, payload)
        except AiError:
            raise
        except Exception as exc:  # noqa: BLE001 - toute panne devient un code exploitable
            raise AiError(
                "AI_CALL_FAILED",
                "L'appel au modèle n'a pas abouti. Le travail reste reprenable une fois la "
                f"cause corrigée ({type(exc).__name__}).",
            ) from exc
        duration = int((time.monotonic() - started) * 1000)

        return AiResponse(
            role=request.role,
            model_id=model_id,
            content=content,
            status="OK",
            duration_ms=duration,
            data_categories=categories,
        )

    def _call(self, model_id: str, request: AiRequest) -> dict:
        """Appel effectif. Le client est injecté : il n'est jamais construit ici."""
        if self._client is None:
            raise ExternalAiNotConfigured(
                "aucun client n'est injecté dans le fournisseur hybride."
            )
        try:
            return self._client.complete(model_id=model_id, request=request)
        except LookupError as exc:  # le client signale un modèle inconnu
            raise ModelUnavailable(model_id) from exc


def get_provider(*, client=None) -> AIProvider:
    """Retourne le fournisseur correspondant au mode configuré.

    Le client réel n'est construit que dans le mode hybride, et seulement si
    l'appelant n'en fournit pas : en `LOCAL_ONLY`, rien qui sache parler à
    l'extérieur n'est même instancié. L'import est local pour la même raison.
    """
    mode = get_settings().analysis_mode
    if mode == LOCAL_MODEL:
        return LocalModelProvider(client=client)
    if mode == HYBRID_STRICT:
        if client is None:
            from app.services.ai_client import AnthropicClient

            client = AnthropicClient()
        return HybridStrictProvider(client=client)
    return LocalOnlyProvider()


def record_call(
    session: Session,
    *,
    dossier_id: str | None,
    job_id: str | None,
    role: str,
    model_id: str,
    status: str,
    duration_ms: int | None = None,
    input_payload: str | None = None,
    output_payload: str | None = None,
    data_categories: list[str] | None = None,
    error_code: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> AiCall:
    """Journalise l'appel — empreintes et catégories, jamais le contenu."""
    row = AiCall(
        id=new_id(),
        dossier_id=dossier_id,
        job_id=job_id,
        role=role,
        model_id=model_id,
        prompt_version=PROMPT_VERSION,
        status=status,
        duration_ms=duration_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_sha256=_sha256(input_payload) if input_payload else None,
        output_sha256=_sha256(output_payload) if output_payload else None,
        data_categories=json.dumps(data_categories or [], ensure_ascii=False),
        error_code=error_code,
    )
    session.add(row)
    session.flush()
    return row


def status() -> dict:
    """État du mode d'analyse, affichable dans l'interface."""
    provider = get_provider()
    described = provider.describe()
    described["modes"] = list(MODES)
    # Le mode recommandé est celui qui lit **sans rien faire sortir** : pour une
    # commission qui traite des dossiers confidentiels, c'est la seule
    # recommandation défendable, et elle ne coûte ni clé ni abonnement.
    described["recommended"] = LOCAL_MODEL
    described["identity_documents_transmitted"] = False
    described["original_pdf_transmitted"] = False
    return described
