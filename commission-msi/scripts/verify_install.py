"""Vérification d'installation — dire si l'application peut réellement lire.

Ce script existe à cause d'un cas réel. Une installation s'est terminée sur
« Installation terminée », alors que **rien ne pouvait être lu** : Tesseract
était absent et RapidOCR avait échoué à s'installer. L'évaluateur a versé son
dossier, a cliqué, et l'application lui a répondu que sa page était illisible.

Un message de fin d'installation qui ne dit que « terminé » est donc trompeur.
Ce script répond à la seule question qui compte : *cette installation lit-elle
quelque chose, et quoi ?* Il ne se contente pas d'inventorier des paquets — il
**fait lire deux images de contrôle**, une latine et une arabe, et rapporte ce
qui en sort.

Il peut être relancé à tout moment :

    backend\\.venv\\Scripts\\python.exe scripts\\verify_install.py

Designed by Prof. Merzoug Mohamed.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

#: Limite historique de Windows. Elle s'applique au chemin complet d'un
#: fichier, pas au répertoire d'installation : c'est la profondeur des
#: dépendances qui consomme le reste.
MAX_PATH = 260

#: Suffixe le plus long observé dans les dépendances, mesuré sur l'échec réel
#: d'`onnxruntime` (`...\\ort_flatbuffers_py\\fbs\\DeprecatedNodeIndexAndKernelDefHash.py`).
DEEPEST_DEPENDENCY_SUFFIX = 129

#: Marge conservée pour les dépendances non encore rencontrées.
PATH_SAFETY_MARGIN = 30

LATIN_LINES = ("DEMANDE D'ORGANISATION", "Colloque international 2027")
ARABIC_LINES = ("الجمهورية الجزائرية الديمقراطية الشعبية", "وزارة التعليم العالي و البحث العلمي")

ARABIC_FONTS = (
    "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\times.ttf",
)
LATIN_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    r"C:\Windows\Fonts\arial.ttf",
)

OK = "  [OK]   "
WARN = "  [!]    "
FAIL = "  [ECHEC]"


def _render(lines: tuple[str, ...], fonts: tuple[str, ...]) -> bytes | None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    font = None
    for candidate in fonts:
        try:
            font = ImageFont.truetype(candidate, 36)
            break
        except OSError:
            continue
    if font is None:
        return None

    image = Image.new("L", (1000, 240), 255)
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        draw.text((40, 30 + index * 90), line, fill=20, font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def check_path_length(report: list[str]) -> bool:
    """Le chemin d'installation laisse-t-il la place aux dépendances ?"""
    root = str(ROOT)
    budget = MAX_PATH - DEEPEST_DEPENDENCY_SUFFIX - PATH_SAFETY_MARGIN
    if len(root) <= budget:
        report.append(f"{OK} Chemin d'installation : {len(root)} caractères (limite {budget}).")
        return True

    report.append(
        f"{FAIL} Chemin d'installation trop long : {len(root)} caractères, "
        f"maximum conseillé {budget}."
    )
    report.append(
        "         Windows refuse tout fichier dépassant 260 caractères au total. "
        "Les dépendances ajoutent jusqu'à 129 caractères après ce chemin, donc "
        "l'installation de RapidOCR échoue silencieusement en cours de route."
    )
    report.append("         Deux remèdes, l'un ou l'autre suffit :")
    report.append(
        "           1. déplacez le dossier vers un chemin court, par exemple "
        "C:\\CommissionMSI, puis relancez install_windows.bat ;"
    )
    report.append(
        "           2. ou activez les chemins longs de Windows, en PowerShell "
        "administrateur :"
    )
    report.append(
        '              New-ItemProperty -Path "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\'
        'FileSystem" -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force'
    )
    report.append("              puis redémarrez le poste et relancez install_windows.bat.")
    return False


def check_long_paths_enabled(report: list[str]) -> None:
    """Information complémentaire, uniquement sous Windows."""
    if sys.platform != "win32":
        return
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem"
        ) as handle:
            value, _kind = winreg.QueryValueEx(handle, "LongPathsEnabled")
        if int(value) == 1:
            report.append(f"{OK} Chemins longs Windows : activés.")
        else:
            report.append(f"{WARN} Chemins longs Windows : désactivés.")
    except OSError:
        report.append(f"{WARN} Chemins longs Windows : désactivés (clé absente).")


def check_engines(report: list[str]) -> tuple[bool, bool]:
    """Renvoie (latin lisible, arabe lisible), mesurés et non supposés."""
    from app.services import ocr_engines, ocr_service

    tesseract = ocr_service.is_available()
    languages = ocr_service.installed_languages() if tesseract else []
    rapid = ocr_engines.rapidocr_available()

    if tesseract:
        report.append(f"{OK} Tesseract : présent, langues {', '.join(languages) or 'aucune'}.")
        if ocr_engines.ARABIC_LANGUAGE in languages:
            report.append(f"{OK} Paquet arabe « ara » : présent.")
        else:
            report.append(f"{FAIL} Paquet arabe « ara » : ABSENT.")
            report.append(
                "         Aucune page arabe ne pourra être lue. Réexécutez "
                "l'installateur Tesseract en cochant « Additional language data » "
                "puis Arabic, ou copiez ara.traineddata dans le dossier tessdata."
            )
    else:
        report.append(f"{FAIL} Tesseract : ABSENT.")
        report.append(
            "         C'est le seul moteur local capable de lire l'arabe. "
            "Téléchargez-le sur https://github.com/UB-Mannheim/tesseract/wiki "
            "et cochez « Additional language data » : Arabic, French, English."
        )

    if rapid:
        report.append(f"{OK} RapidOCR : présent (latin et chinois ; ne lit pas l'arabe).")
    else:
        report.append(f"{WARN} RapidOCR : absent. Second avis local indisponible.")

    latin_ok = arabic_ok = False

    latin_png = _render(LATIN_LINES, LATIN_FONTS)
    if latin_png is None:
        report.append(f"{WARN} Lecture latine : non testée (police de contrôle absente).")
    else:
        outcome = ocr_engines.read_page(latin_png)
        latin_ok = any(line in outcome.text for line in LATIN_LINES)
        report.append(
            f"{OK if latin_ok else FAIL} Lecture d'une page latine de contrôle : "
            + (f"réussie via {outcome.engine}." if latin_ok else "ÉCHOUÉE.")
        )

    arabic_png = _render(ARABIC_LINES, ARABIC_FONTS)
    if arabic_png is None:
        report.append(f"{WARN} Lecture arabe : non testée (police de contrôle absente).")
    else:
        outcome = ocr_engines.read_page(arabic_png)
        arabic_ok = any(line in outcome.text for line in ARABIC_LINES)
        report.append(
            f"{OK if arabic_ok else FAIL} Lecture d'une page arabe de contrôle : "
            + (f"réussie via {outcome.engine}." if arabic_ok else "ÉCHOUÉE.")
        )

    return latin_ok, arabic_ok


def check_application(report: list[str]) -> bool:
    try:
        from app.core.config import get_settings

        settings = get_settings()
    except Exception as exc:  # noqa: BLE001 - le message doit rester lisible
        report.append(f"{FAIL} L'application ne démarre pas : {type(exc).__name__} — {exc}")
        return False

    report.append(f"{OK} Application importable, version {settings.version}.")
    if (ROOT / "frontend" / "dist" / "index.html").is_file():
        report.append(f"{OK} Interface compilée présente.")
    else:
        report.append(f"{FAIL} Interface compilée absente : l'écran restera vide.")
        report.append("         Exécutez « npm run build » dans le dossier frontend.")
        return False
    return True


def main() -> int:
    report: list[str] = []

    print()
    print("=== Vérification de l'installation — Commission MSI ===")
    print()

    path_ok = check_path_length(report)
    check_long_paths_enabled(report)
    app_ok = check_application(report)
    latin_ok, arabic_ok = check_engines(report)

    for line in report:
        print(line)

    print()
    print("--- Verdict ---")
    if not app_ok:
        print("  L'application ne peut pas démarrer. Corrigez les points ci-dessus.")
        return 2

    if latin_ok and arabic_ok:
        print("  Lecture opérationnelle en latin ET en arabe. Rien ne manque.")
        return 0

    if latin_ok and not arabic_ok:
        print(
            "  ATTENTION : les pages latines sont lues, PAS les pages arabes.\n"
            "  Un dossier algérien contient presque toujours des pages en arabe :\n"
            "  elles ressortiront « non extraites » tant que le paquet « ara »\n"
            "  de Tesseract n'est pas installé. Ce n'est pas un défaut des pages."
        )
        return 1

    print(
        "  ATTENTION : AUCUNE page scannée ne peut être lue sur ce poste.\n"
        "  L'application fonctionnera, mais toute page sans texte natif restera\n"
        "  vide et marquée « vérification humaine obligatoire ».\n"
        "  Installez Tesseract avec ses paquets ara, fra et eng."
    )
    if not path_ok:
        print("  Traitez d'abord le chemin d'installation trop long, ci-dessus.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
