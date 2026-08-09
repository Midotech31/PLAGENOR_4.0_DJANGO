"""Client d'un modèle de langage **installé sur le poste** (serveur Ollama).

Pourquoi ce chemin est le bon, et pas un pis-aller
--------------------------------------------------

Cette application existe pour qu'un dossier de commission ne quitte jamais le
poste. Un modèle qui tourne localement respecte cette exigence **mieux** que le
mode hybride : rien ne sort, pas même un extrait expurgé, pas même vers un
fournisseur de confiance. Il n'y a ni clé, ni compte, ni facture, ni dépendance
à un service qui peut changer ses conditions.

Ce que ce chemin coûte, et qu'il faut dire
------------------------------------------

Un modèle de 7 milliards de paramètres tournant sur un poste bureautique lit
moins bien qu'un modèle de service. Il se trompe plus souvent, produit parfois
un JSON malformé, et lit l'arabe moins bien que le français.

**Cela ne le rend pas dangereux ici, et la raison est structurelle.** Chaque
valeur proposée doit citer une page *et* un extrait, relu mot pour mot sur le
texte local. Une valeur inventée ne passe pas ce contrôle : elle est rejetée et
comptée. Le mode de défaillance d'un modèle faible est donc **« moins de champs
extraits »**, jamais « des champs faux acceptés ». C'est ce qui rend un petit
modèle utilisable pour ce travail alors qu'il ne le serait pas dans une
architecture qui lui ferait confiance.

Deux réglages qui ne se devinent pas
------------------------------------

* **`num_ctx`** : la valeur par défaut d'Ollama tronque silencieusement les
  longues entrées. Un modèle qui répond sur un texte amputé sans le signaler
  produirait des « non vérifiable » injustifiés. La fenêtre est donc toujours
  demandée explicitement ;
* **`format: "json"`** : Ollama contraint alors la sortie à être du JSON valide.
  C'est ce qui rend un petit modèle exploitable pour de l'extraction
  structurée, là où il produirait sinon du texte mêlé de commentaires.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.core.config import get_settings

#: Chemin de l'API de conversation d'Ollama.
CHAT_PATH = "/api/chat"

#: Chemin listant les modèles réellement installés sur le poste.
TAGS_PATH = "/api/tags"

#: Plafond de jetons produits. Une extraction structurée est courte.
MAX_OUTPUT_TOKENS = 4096


class LocalModelClient:
    """Client du serveur de modèle local, injecté dans `LocalModelProvider`."""

    def __init__(self, *, base_url: str | None = None, opener=None) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._opener = opener or urllib.request.build_opener()

    def _url(self, path: str) -> str:
        base = self._base_url or get_settings().local_model_url.rstrip("/")
        return f"{base}{path}"

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def installed_models(self) -> list[str]:
        """Modèles réellement présents sur le poste.

        Sert à distinguer « le serveur ne répond pas » de « le modèle demandé
        n'est pas téléchargé » — deux pannes qui se corrigent différemment.
        """
        request = urllib.request.Request(self._url(TAGS_PATH), method="GET")  # noqa: S310
        try:
            with self._opener.open(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"le serveur de modèle local ne répond pas ({exc.reason}). "
                "Vérifiez qu'Ollama est démarré."
            ) from exc
        except Exception as exc:  # noqa: BLE001 - réponse illisible
            raise RuntimeError("réponse illisible du serveur de modèle local") from exc

        return [
            str(entry.get("name") or entry.get("model") or "")
            for entry in payload.get("models") or []
            if isinstance(entry, dict)
        ]

    # ------------------------------------------------------------------
    # Appel
    # ------------------------------------------------------------------

    def complete(self, *, model_id: str, request) -> dict:
        """Envoie la requête au modèle local et renvoie le JSON produit."""
        settings = get_settings()

        body = json.dumps(
            {
                "model": model_id,
                "stream": False,
                # Sortie contrainte : un petit modèle rendrait sinon du texte
                # mêlé de commentaires, inexploitable pour de l'extraction.
                "format": "json",
                "messages": [
                    {"role": "system", "content": request.instruction},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"blocs": request.blocks, "schema": request.json_schema},
                            ensure_ascii=False,
                        ),
                    },
                ],
                "options": {
                    # Fenêtre demandée explicitement : la valeur par défaut
                    # tronquerait les pages sans rien signaler.
                    "num_ctx": settings.local_model_context,
                    "num_predict": MAX_OUTPUT_TOKENS,
                    "temperature": 0,
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")

        http = urllib.request.Request(  # noqa: S310 - boucle locale
            self._url(CHAT_PATH),
            data=body,
            method="POST",
            headers={"content-type": "application/json"},
        )

        try:
            with self._opener.open(http, timeout=settings.local_model_timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = self._safe_detail(exc)
            if exc.code == 404:
                # Ollama répond 404 pour un modèle absent : c'est une erreur de
                # configuration, pas une panne. Le fournisseur la traduira en
                # `ModelUnavailable`.
                raise LookupError(
                    f"le modèle « {model_id} » n'est pas installé sur ce poste ({detail})"
                ) from exc
            raise RuntimeError(f"appel refusé (HTTP {exc.code}) : {detail}") from exc
        except TimeoutError as exc:
            # Cause la plus fréquente sur un poste sans carte graphique, et la
            # seule qui ne se voit pas : le modèle travaille, simplement trop
            # lentement pour le délai. La confondre avec une panne ferait
            # chercher du côté du serveur, qui va parfaitement bien.
            raise RuntimeError(
                f"le modèle local n'a pas répondu en {settings.local_model_timeout} secondes. "
                "Il n'est pas en panne : il est trop lent pour ce poste. "
                f"Trois remèdes, du plus efficace au plus simple : un modèle plus petit "
                f"(ollama pull qwen2.5:7b puis setx MSI_LOCAL_MODEL qwen2.5:7b), une fenêtre "
                f"de contexte plus courte (setx MSI_LOCAL_MODEL_CONTEXT 4096, qui divise "
                f"la taille de chaque lot), ou un délai plus large "
                f"(setx MSI_LOCAL_MODEL_TIMEOUT 3600)."
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise RuntimeError(
                    f"le modèle local n'a pas répondu en {settings.local_model_timeout} "
                    "secondes. Il n'est pas en panne : il est trop lent pour ce poste. "
                    "Essayez un modèle plus petit (ollama pull qwen2.5:7b puis "
                    "setx MSI_LOCAL_MODEL qwen2.5:7b), une fenêtre plus courte "
                    "(setx MSI_LOCAL_MODEL_CONTEXT 4096) ou un délai plus large "
                    "(setx MSI_LOCAL_MODEL_TIMEOUT 3600)."
                ) from exc
            raise RuntimeError(
                f"le serveur de modèle local ne répond pas ({exc.reason}). "
                "Vérifiez qu'Ollama est démarré."
            ) from exc

        return self._extract_json(payload)

    @staticmethod
    def _safe_detail(exc: urllib.error.HTTPError) -> str:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - un corps illisible n'est pas une panne
            return exc.reason or "motif non fourni"
        if isinstance(body, dict) and body.get("error"):
            return str(body["error"])[:300]
        return exc.reason or "motif non fourni"

    @staticmethod
    def _extract_json(payload: dict) -> dict:
        """Retient l'objet JSON produit, sans jamais conserver de raisonnement.

        Certains modèles locaux encadrent leur réponse d'un bloc `<think>` : il
        est retiré à la lecture et jamais écrit, comme la chaîne de pensée d'un
        modèle de service.
        """
        message = payload.get("message")
        text = ""
        if isinstance(message, dict):
            text = str(message.get("content") or "")
        text = text.strip()

        if "</think>" in text:
            text = text.split("</think>", 1)[-1].strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        if not text:
            raise RuntimeError("réponse vide du modèle local")

        try:
            content = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "le modèle local n'a pas renvoyé un JSON exploitable ; aucune valeur "
                "n'est retenue"
            ) from exc

        if not isinstance(content, dict):
            raise RuntimeError("le modèle local a renvoyé un JSON qui n'est pas un objet")
        return content
