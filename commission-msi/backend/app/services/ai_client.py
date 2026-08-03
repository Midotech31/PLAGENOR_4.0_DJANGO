"""Client Anthropic réel — le seul endroit du code qui parle à l'extérieur.

`HybridStrictProvider` refusait jusqu'ici de fonctionner faute de client :
`_call` exigeait qu'on lui en injecte un, et aucun n'existait. Le mode
`HYBRID_STRICT` était donc une façade — configurable, jamais opérante. Ce
module comble ce manque.

Ce qu'il fait, et ce qu'il ne fait pas :

* **il ne décide rien.** Il transmet des blocs déjà expurgés par le
  fournisseur, reçoit du JSON, et le rend tel quel. Le tri, la validation et
  le refus appartiennent à l'appelant ;
* **il ne lit jamais la clé ailleurs que dans la configuration**, qui la prend
  elle-même dans l'environnement ou le coffre du système. Elle n'apparaît ni
  en clair dans le code, ni dans un message d'erreur, ni dans un journal ;
* **il ne conserve pas le raisonnement du modèle.** Seule la réponse
  structurée est rendue. Si le modèle produit une chaîne de pensée, elle est
  ignorée à la lecture et jamais écrite ;
* **il ne réessaie pas indéfiniment.** Une panne devient une erreur nommée que
  le travail durable sait reprendre, plutôt qu'une boucle silencieuse.

L'appel se fait avec la bibliothèque standard, comme le reste des sorties de
cette application : ajouter une dépendance pour un seul POST HTTPS
augmenterait la surface d'installation sans rien apporter, et l'installation
sous Windows est déjà le point le plus fragile de ce projet.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.core.config import get_settings

#: Point d'entrée de l'API Messages. Nommé ici, jamais construit dynamiquement.
ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"

#: Version d'API exigée par l'en-tête `anthropic-version`.
ANTHROPIC_API_VERSION = "2023-06-01"

#: Plafond de jetons produits. Il couvre **le raisonnement et la réponse** : sur
#: les modèles récents, la réflexion est active par défaut et se compte dans ce
#: plafond. Un plafond serré tronquerait la réponse au milieu d'un champ.
MAX_OUTPUT_TOKENS = 16000

#: Modèles pour lesquels l'API accepte un repli automatique en cas de refus de
#: ses classificateurs de sécurité. Le repli est demandé pour ceux-là seulement :
#: l'envoyer à un modèle qui ne le connaît pas ferait échouer la requête.
FALLBACK_CAPABLE = ("claude-opus-5", "claude-fable-5", "claude-mythos-5")

#: En-tête d'activation du repli automatique.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

#: Au-delà, l'appel est abandonné : le travail durable le reprendra plutôt que
#: de bloquer le poste de l'évaluateur sur une requête qui n'aboutit pas.
TIMEOUT_SECONDS = 120


class AnthropicClient:
    """Client minimal de l'API Messages, injecté dans `HybridStrictProvider`."""

    def __init__(self, *, endpoint: str = ANTHROPIC_ENDPOINT, opener=None) -> None:
        self._endpoint = endpoint
        # L'ouvreur est injectable pour les tests : aucun test ne doit sortir.
        self._opener = opener or urllib.request.build_opener()

    def complete(self, *, model_id: str, request) -> dict:
        """Envoie la requête et renvoie le JSON produit par le modèle.

        `LookupError` est levée pour un modèle inconnu : le fournisseur la
        traduit en `ModelUnavailable`, ce qui évite qu'un identifiant erroné
        ressemble à une panne réseau.
        """
        settings = get_settings()
        key = settings.anthropic_api_key
        if not key:
            # Ne devrait pas survenir : `available()` l'a déjà vérifié. Le
            # redire ici évite qu'une évolution du fournisseur ouvre un trou.
            raise LookupError("aucune clé API n'est configurée")

        payload_body: dict = {
            "model": model_id,
            "max_tokens": MAX_OUTPUT_TOKENS,
            # Aucun réglage d'échantillonnage : `temperature`, `top_p` et `top_k`
            # sont refusés par les modèles récents et feraient échouer l'appel.
            # La stabilité d'une extraction vient de l'instruction et de la
            # vérification des extraits, pas d'un réglage de variabilité.
            "system": request.instruction,
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(
                        {"blocs": request.blocks, "schema": request.json_schema},
                        ensure_ascii=False,
                    ),
                }
            ],
        }

        headers = {
            "content-type": "application/json",
            "anthropic-version": ANTHROPIC_API_VERSION,
            "x-api-key": key,
        }

        # Un classificateur de sécurité peut refuser une requête pourtant
        # légitime. Sur les modèles qui le permettent, l'API réessaie alors
        # d'elle-même sur un modèle de repli : le dossier est analysé au lieu
        # d'être bloqué sur un faux positif.
        if model_id.startswith(FALLBACK_CAPABLE):
            payload_body["fallbacks"] = "default"
            headers["anthropic-beta"] = FALLBACK_BETA

        body = json.dumps(payload_body, ensure_ascii=False).encode("utf-8")

        http = urllib.request.Request(  # noqa: S310 - point d'entrée nommé en dur
            self._endpoint,
            data=body,
            method="POST",
            headers=headers,
        )

        try:
            with self._opener.open(http, timeout=TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = self._safe_detail(exc)
            if exc.code == 404 or "model" in detail.lower():
                raise LookupError(f"modèle refusé par l'API : {detail}") from exc
            # Le corps d'erreur peut contenir la requête : il n'est pas recopié.
            raise RuntimeError(f"appel refusé (HTTP {exc.code}) : {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"appel impossible : {exc.reason}") from exc

        return self._extract_json(payload)

    @staticmethod
    def _safe_detail(exc: urllib.error.HTTPError) -> str:
        """Motif d'erreur lisible, sans recopier le corps de la requête.

        Un corps d'erreur d'API peut renvoyer l'entrée en écho ; la journaliser
        rendrait au journal ce que l'expurgation vient d'en retirer.
        """
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - un corps illisible n'est pas une panne
            return exc.reason or "motif non fourni"
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            return str(error.get("type") or error.get("message") or exc.reason)
        return exc.reason or "motif non fourni"

    @staticmethod
    def _extract_json(payload: dict) -> dict:
        """Retient le JSON produit, en ignorant tout raisonnement éventuel.

        Les blocs `thinking` sont explicitement écartés : le prompt maître
        interdit de conserver ou d'afficher la chaîne de pensée du modèle.
        """
        # Un refus est une réponse valide (HTTP 200), pas une panne : le champ
        # `content` peut être vide. Le lire sans vérifier produirait une erreur
        # trompeuse au lieu du motif réel.
        if payload.get("stop_reason") == "refusal":
            raise RuntimeError(
                "la requête a été refusée par les filtres du fournisseur ; aucune valeur "
                "n'est retenue. Le dossier reste analysable en mode LOCAL_ONLY."
            )

        pieces: list[str] = []
        for block in payload.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "text":
                continue  # « thinking » et autres blocs sont ignorés, jamais lus
            pieces.append(str(block.get("text") or ""))

        text = "\n".join(pieces).strip()
        if not text:
            raise RuntimeError("réponse vide du modèle")

        # Le modèle encadre parfois le JSON d'un bloc de code ; on le retire
        # sans tenter d'interpréter autre chose.
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[: -3]
            text = text.strip()

        try:
            content = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "le modèle n'a pas renvoyé un JSON exploitable ; aucune valeur n'est retenue"
            ) from exc

        if not isinstance(content, dict):
            raise RuntimeError("le modèle a renvoyé un JSON qui n'est pas un objet")
        return content
