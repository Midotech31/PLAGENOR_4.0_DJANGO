"""Vérifie l'état du mode d'analyse, et le prouve par un appel si demandé.

« Le mode est configuré » ne veut rien dire tant qu'aucun appel n'a abouti :
une clé révoquée, un identifiant de modèle erroné ou un pare-feu d'entreprise
produisent exactement la même configuration apparente qu'une installation qui
fonctionne. Ce script fait la différence.

Avec `--appel`, il transmet **une phrase de test**, jamais un dossier. C'est
délibéré : vérifier la chaîne ne doit pas exposer une donnée réelle.

Codes de sortie : `0` si l'état est celui attendu, `1` sinon.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


#: Longueur de chemin au-delà de laquelle l'installation des dépendances échoue
#: sous Windows. Identique au seuil de `install_windows.bat`, et pour la même
#: raison : les dépendances ajoutent jusqu'à 129 caractères après ce dossier,
#: pour un maximum absolu de 260.
MAX_PATH_BUDGET = 101


def _title(text: str) -> None:
    print(f"\n{text}\n{'-' * len(text)}")


def _explain_missing_environment(exc: ModuleNotFoundError) -> int:
    """Traduit une dépendance absente en cause probable et en remède.

    Un `ModuleNotFoundError` brut fait chercher du côté de la clé ou du réseau,
    alors que rien n'a encore été tenté : l'environnement Python lui-même n'est
    pas en état. Sur un chemin trop long, la cause est presque toujours la même
    et le remède ne se devine pas.
    """
    racine = Path(__file__).resolve().parents[1]
    longueur = len(str(racine))

    _title("[ECHEC] L'environnement Python n'est pas installé")
    print(f"Dépendance absente : {exc.name}.")
    print()
    print("Ni la clé API ni le modèle ne sont en cause : aucun appel n'a été tenté.")
    print("Les bibliothèques dont l'application a besoin ne sont pas installées.")
    print()

    if longueur > MAX_PATH_BUDGET:
        print(f"Cause probable : le chemin d'installation fait {longueur} caractères,")
        print(f"pour un maximum conseillé de {MAX_PATH_BUDGET}.")
        print(f"  {racine}")
        print()
        print("Windows refuse tout fichier dépassant 260 caractères au total, et les")
        print("dépendances ajoutent jusqu'à 129 caractères après ce dossier.")
        print("L'installation a donc échoué en cours de route.")
        print()
        print("Remède : déplacez ce dossier vers un chemin court, par exemple")
        print("C:\\CommissionMSI, puis relancez install_windows.bat depuis là.")
        print("Vos réglages de mode et votre clé API survivent au déplacement :")
        print("ils sont dans l'environnement Windows, pas dans le dossier.")
    else:
        print("Remède : relancez install_windows.bat, et lisez la fin de son")
        print("exécution — si une erreur y figure, c'est elle qu'il faut traiter.")
    return 1


def main(argv: list[str]) -> int:
    try:
        from app.services import ai_provider
    except ModuleNotFoundError as exc:
        # L'environnement n'est pas en état : le dire plutôt que de laisser
        # remonter une trace technique qui n'apprend rien à l'évaluateur.
        return _explain_missing_environment(exc)

    state = ai_provider.status()
    mode = state["mode"]

    _title(f"Mode d'analyse : {mode}")
    print(state["notice"])
    print()
    print(f"  PDF original transmis .................. {'non'}")
    print(f"  Pièces d'identité transmises ........... {'non'}")
    print(f"  Modèle configuré ....................... {state.get('model_id') or '—'}")

    if mode == ai_provider.LOCAL_ONLY:
        print()
        print("[OK] Aucune sortie externe n'est possible dans ce mode.")
        print(
            "     La lecture sémantique assistée est inactive : les informations\n"
            "     rédigées en prose ou en tableau peuvent rester non extraites."
        )
        return 0

    missing = state.get("missing") or []
    if missing:
        print()
        print("[ECHEC] Le mode HYBRID_STRICT est incomplet. Manque :")
        for item in missing:
            print(f"  - {item}")
        print()
        print("Relancez activer_hybrid_strict.bat après correction.")
        return 1

    print()
    print("[OK] La configuration est complète.")

    if "--appel" not in argv:
        print(
            "     Aucun appel n'a été tenté : la configuration peut être complète\n"
            "     et la clé néanmoins refusée. Relancez avec --appel pour le savoir."
        )
        return 0

    _title("Appel de contrôle")
    print("Une phrase de test est transmise. Aucun dossier n'est envoyé.")

    provider = ai_provider.get_provider()
    request = ai_provider.AiRequest(
        role="CONTROLE_INSTALLATION",
        instruction=(
            "Tu vérifies une installation. Réponds uniquement par l'objet JSON "
            '{"ok": true, "lu": "<le mot cité dans le bloc>"} sans texte autour.'
        ),
        blocks=[
            {
                "evidence_id": "controle",
                "kind": "text/plain",
                "sensitivity": "ORDINAIRE",
                "text": "Le mot à citer est : concordance.",
            }
        ],
        json_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
    )

    try:
        response = provider.complete(request)
    except ai_provider.AiError as exc:
        print()
        print(f"[ECHEC] {exc.code} — {exc}")
        print()
        if exc.code == "MODEL_UNAVAILABLE":
            print(
                "Corrigez ANTHROPIC_MODEL_ANALYSIS : l'identifiant doit être exact,\n"
                "et le modèle accessible à ce compte. Aucun repli vers un modèle\n"
                "moins performant n'est fait — ce serait vous faire croire à un\n"
                "résultat produit par le modèle que vous aviez choisi."
            )
        else:
            print(
                "Vérifiez, dans cet ordre : la clé API, l'accès réseau sortant vers\n"
                "api.anthropic.com, puis un éventuel proxy d'établissement."
            )
        return 1

    read = str(response.content.get("lu", "")).strip().lower()
    print()
    print(f"  Modèle ayant répondu ................... {response.model_id}")
    print(f"  Durée de l'appel ....................... {response.duration_ms} ms")
    print(f"  Catégories transmises .................. {', '.join(response.data_categories)}")
    print()

    if "concordance" not in read:
        # Le modèle a répondu mais n'a pas lu le bloc : la chaîne fonctionne,
        # la lecture non. Le dire vaut mieux qu'un « OK » qui ne prouve rien.
        print(
            "[AVERTISSEMENT] L'appel a abouti mais le modèle n'a pas restitué le mot\n"
            "du bloc transmis. La liaison fonctionne ; la lecture du contenu n'est\n"
            "pas démontrée. Vérifiez l'identifiant du modèle."
        )
        return 1

    print("[OK] Appel réussi, contenu transmis et relu par le modèle.")
    print(
        "     La lecture sémantique assistée s'exécutera à l'étape « Lecture\n"
        "     sémantique assistée du dossier » du traitement."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
