"""Rendre l'arabe lisible sur ce poste, en une commande.

Pourquoi ce script existe : sur un poste réel, l'arabe est resté illisible
malgré deux tentatives, parce que l'installateur Windows de Tesseract cache
l'arabe derrière une case à cocher — « Additional language data » — qu'il faut
déplier, et que personne ne déplie. Répéter la consigne n'a pas suffi ; autant
faire le travail.

Ce que le script fait, dans l'ordre :

1. il constate l'état réel — Tesseract présent ou non, langues installées ;
2. si Tesseract est là mais sans l'arabe, il **installe le paquet lui-même** :
   il localise le dossier `tessdata` que Tesseract utilise réellement, y dépose
   `ara.traineddata` depuis le dépôt officiel, et **revérifie en interrogeant
   Tesseract** — pas en supposant que le téléchargement a suffi ;
3. si Tesseract est absent, il ne peut pas l'installer à la place de
   l'utilisateur, mais il cherche `winget` et donne la commande exacte plutôt
   qu'un lien vers une page.

Ce qu'il ne fait pas : prétendre. Chaque étape est vérifiée sur le comportement
de Tesseract, jamais sur la présence d'un fichier.

    backend\\.venv\\Scripts\\python.exe scripts\\installer_arabe.py

Designed by Prof. Merzoug Mohamed.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

#: Modèles arabes officiels du projet Tesseract, essayés dans l'ordre.
#:
#: Plusieurs adresses parce qu'une seule est un point de rupture unique : la
#: forme `github.com/.../raw/...` a été mesurée renvoyant 403 derrière un
#: mandataire d'entreprise, là où `raw.githubusercontent.com` passe. Un poste
#: administratif est précisément le genre d'endroit où l'un marche et l'autre
#: non.
#:
#: `tessdata_fast` d'abord : 1,4 Mo contre 2,4 Mo, sensiblement plus rapide, et
#: la différence de justesse est marginale sur des documents administratifs
#: nets. Le modèle complet sert de recours.
ARABIC_MODEL_URLS = (
    "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/ara.traineddata",
    "https://github.com/tesseract-ocr/tessdata_fast/raw/main/ara.traineddata",
    "https://raw.githubusercontent.com/tesseract-ocr/tessdata/main/ara.traineddata",
)

#: Identifiant winget du portage Windows de Tesseract, **relevé sur un poste
#: réel** et non supposé : `winget search tesseract` y a renvoyé
#: `UB-Mannheim.TesseractOCR 5.4.0.20240606`. C'est le portage que la
#: documentation du projet recommande sous Windows.
#:
#: L'installation par winget prend les options par défaut, qui n'incluent que
#: l'anglais : c'est précisément pourquoi ce script existe et pose l'arabe
#: ensuite.
WINGET_PACKAGE = "UB-Mannheim.TesseractOCR"

#: En deçà, le fichier récupéré n'est pas un modèle : c'est une page d'erreur
#: ou une redirection. Le modèle arabe pèse environ 1,4 Mo.
MIN_MODEL_BYTES = 500_000

#: Première ligne de `tesseract --list-langs` : elle nomme le dossier que le
#: moteur utilise réellement. Le deviner à partir du chemin du binaire serait
#: faux dès que `TESSDATA_PREFIX` est défini.
TESSDATA_LINE = re.compile(r'"([^"]+)"')


def _tesseract() -> str | None:
    from app.services import ocr_service

    return ocr_service.tesseract_command()


def _languages(command: str) -> tuple[list[str], str | None]:
    """Langues installées et dossier tessdata, tels que Tesseract les voit."""
    try:
        output = subprocess.run(  # noqa: S603 - binaire local explicite
            [command, "--list-langs"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  [ECHEC] Tesseract n'a pas répondu : {exc}")
        return [], None

    lines = (output.stdout or output.stderr or "").splitlines()
    if not lines:
        return [], None
    match = TESSDATA_LINE.search(lines[0])
    directory = match.group(1) if match else None
    return [line.strip() for line in lines[1:] if line.strip()], directory


def _fetch() -> bytes | None:
    """Récupère le modèle depuis la première adresse qui répond correctement."""
    for url in ARABIC_MODEL_URLS:
        print(f"  Téléchargement depuis {url}")
        try:
            with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310
                payload = response.read()
        except Exception as exc:  # noqa: BLE001 - le motif doit rester lisible
            print(f"          échec : {type(exc).__name__} — {exc}")
            continue
        # Une page d'erreur ou une redirection pèse quelques centaines d'octets.
        # L'accepter installerait un fichier illisible que Tesseract refuserait
        # ensuite sans expliquer pourquoi.
        if len(payload) < MIN_MODEL_BYTES:
            print(f"          échec : {len(payload)} octets reçus, ce n'est pas le modèle.")
            continue
        return payload

    print("  [ECHEC] Aucune adresse n'a fourni le modèle.")
    print("          Si ce poste passe par un mandataire, téléchargez le fichier")
    print("          depuis un poste connecté et copiez-le à la main dans le")
    print("          dossier tessdata indiqué plus haut :")
    print(f"              {ARABIC_MODEL_URLS[0]}")
    return None


def _download(target: Path) -> bool:
    payload = _fetch()
    if payload is None:
        return False
    temporary = target.with_suffix(".part")

    try:
        temporary.write_bytes(payload)
        temporary.replace(target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        print(f"  [ECHEC] Écriture impossible dans {target.parent} : {exc}")
        print("          Relancez cette commande depuis une invite ADMINISTRATEUR.")
        return False

    print(f"  Modèle écrit : {target} ({len(payload) // 1024} Ko)")
    return True


def _install_arabic(command: str, tessdata: str | None) -> bool:
    if not tessdata:
        print("  [ECHEC] Dossier tessdata introuvable : installation automatique impossible.")
        return False

    directory = Path(tessdata)
    if not directory.is_dir():
        print(f"  [ECHEC] {directory} n'existe pas.")
        return False

    if not _download(directory / "ara.traineddata"):
        return False

    # Le seul contrôle qui vaille : redemander à Tesseract ce qu'il sait lire.
    languages, _ = _languages(command)
    if "ara" in languages:
        print("  [OK]    Tesseract déclare désormais connaître l'arabe.")
        return True
    print(
        "  [ECHEC] Le fichier est en place mais Tesseract ne voit toujours pas l'arabe. "
        "Un TESSDATA_PREFIX pointant ailleurs en est la cause la plus fréquente."
    )
    return False


def _guide_full_install() -> None:
    print("  Tesseract n'est pas installé : c'est le seul moteur local qui lise l'arabe.")
    winget = shutil.which("winget")
    if winget:
        print("\n  winget est disponible. Installez Tesseract par cette commande :")
        print(f"      winget install --id {WINGET_PACKAGE}")
        print(
            "\n  Cet identifiant a été relevé sur un poste Windows 11 réel. S'il a "
            "changé depuis, retrouvez-le par :"
        )
        print("      winget search tesseract")
    else:
        print("\n  winget est absent. Installateur graphique :")
        print("      https://github.com/UB-Mannheim/tesseract/wiki")
    print(
        "\n  Dans l'installateur graphique, DÉPLIEZ « Additional language data » et "
        "cochez Arabic, French, English. C'est l'étape qui se manque.\n"
        "  Si vous l'oubliez, relancez ce script : il posera l'arabe tout seul."
    )


def main() -> int:
    print()
    print("=== Rendre l'arabe lisible — Commission MSI ===")
    print()

    command = _tesseract()
    if command is None:
        _guide_full_install()
        return 1

    print(f"  [OK]    Tesseract trouvé : {command}")
    languages, tessdata = _languages(command)
    print(f"          Langues installées : {', '.join(languages) or 'aucune'}")
    if tessdata:
        print(f"          Dossier tessdata : {tessdata}")

    if "ara" in languages:
        print("  [OK]    Le paquet arabe est déjà présent : rien à faire.")
    else:
        print("  [!]     Paquet arabe absent — installation en cours.")
        if not _install_arabic(command, tessdata):
            return 2

    # Contrôle final : une vraie page arabe, lue par la chaîne complète.
    print("\n  Contrôle de lecture sur une page arabe de test…")
    try:
        import verify_install  # type: ignore[import-not-found]
    except ImportError:
        sys.path.insert(0, str(ROOT / "scripts"))
        import verify_install  # type: ignore[import-not-found]

    report: list[str] = []
    _latin_ok, arabic_ok = verify_install.check_engines(report)
    for line in report:
        print(line)

    print()
    if arabic_ok:
        print("  L'arabe est lisible sur ce poste. Relancez l'application et le traitement.")
        return 0
    print(
        "  L'arabe reste illisible malgré le paquet. Envoyez-moi ces lignes : la cause "
        "n'est plus l'installation."
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
