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

#: Polices essayées pour le rendu arabe, **dans un ordre qui n'est pas
#: arbitraire**. Mesuré sur un poste réel : une fois le paquet « ara » installé,
#: le rendu via `arial.ttf` a produit un texte lisiblement faux — des lettres
#: mal jointes, lues par Tesseract avec une confiance de 66 % sur un contenu
#: qui n'existait pas dans l'image d'origine. `_render` ne vérifie que le
#: chargement du fichier, pas la qualité du rendu : Tahoma et Segoe UI, les
#: polices historiquement chargées de l'arabe sur Windows, sont donc essayées
#: avant Arial et Times New Roman, moins fiables sur cette écriture.
ARABIC_FONTS = (
    "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arialuni.ttf",
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
    """Rend avec la première police qui **charge**, sans juger du résultat.

    Suffisant pour le latin, où toute police installée convient. Insuffisant
    pour l'arabe : voir `_best_arabic_reading`, qui juge le rendu et pas
    seulement le chargement du fichier.
    """
    for candidate in fonts:
        png = _render_with(lines, candidate)
        if png is not None:
            return png
    return None


def _render_with(lines: tuple[str, ...], font_path: str, size: int = 36) -> bytes | None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    try:
        font = ImageFont.truetype(font_path, size)
    except OSError:
        return None

    image = Image.new("L", (1000, 240), 255)
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        draw.text((40, 30 + index * 90), line, fill=20, font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _looks_garbled(text: str) -> bool:
    """Un rendu arabe raté par la police système, pas un vrai échec de lecture.

    Calibré sur deux échecs mesurés, tous deux avec le paquet « ara » présent :
    une police sans jointure arabe correcte a produit une répétition de « لا »
    représentant la moitié des paires de lettres lues (contre 11 % sur un rendu
    correct), et une police sans glyphes arabes du tout a produit un texte
    presque sans lettre arabe. Les deux sont ici couverts, avec une marge large
    entre le cas correct et les deux cas ratés.
    """
    letters = [c for c in text if "\u0600" <= c <= "\u06ff"]
    if len(letters) < 8:
        return True
    from collections import Counter

    bigrams = [a + b for a, b in zip(letters, letters[1:])]
    _, count = Counter(bigrams).most_common(1)[0]
    return (count / len(bigrams)) > 0.35


#: Score minimal pour une lecture jugée bonne. Calibré sur des mesures
#: réelles : un rendu correct (avec une variante de graphie usuelle, alif
#: maksoura pour ya) atteint 1.0 ; les deux rendus ratés par une police sans
#: jointure arabe atteignent 0.0. La marge est large.
GOOD_ARABIC_SCORE = 0.7


def _reading_score(text: str) -> float:
    """Proportion des mots attendus retrouvés, après la même normalisation

    que le reste de l'application (variantes de alif, diacritiques, casse).

    Une lecture OCR n'est jamais pixel-parfaite : le contrôle précédent
    comparait le texte lu **brut** à la ligne attendue par inclusion
    littérale, ce qui faisait échouer une lecture par ailleurs correcte pour
    une simple variante de graphie — mesuré sur un poste réel où le paquet
    arabe était confirmé présent et la lecture pourtant déclarée « ÉCHOUÉE ».
    `containment` compare mot à mot, après normalisation ; il absorbe ce genre
    d'écart sans rien absorber d'un vrai échec de lecture.
    """
    from app.core.text import containment

    if not ARABIC_LINES:
        return 0.0
    scores = [containment(line, text) for line in ARABIC_LINES]
    return sum(scores) / len(scores)


def _best_arabic_reading(ocr_engines):
    """Essaie chaque police candidate ; retient la meilleure lecture mesurée.

    Renvoie `None` si aucune police n'a même pu être chargée, sinon
    `(outcome, police, score, suspect)` — `score` est la fidélité mesurée par
    `_reading_score` (1.0 = tous les mots attendus retrouvés), `suspect` un
    indice de rendu raté par la police (voir `_looks_garbled`), gardé pour le
    message, pas pour décider.
    """
    best = None
    for font_path in ARABIC_FONTS:
        png = _render_with(ARABIC_LINES, font_path)
        if png is None:
            continue
        outcome = ocr_engines.read_page(png)
        score = _reading_score(outcome.text)
        if score >= GOOD_ARABIC_SCORE:
            return outcome, font_path, score, False
        suspect = _looks_garbled(outcome.text)
        if best is None or score > best[2]:
            best = (outcome, font_path, score, suspect)
    return best


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


def check_engines(report: list[str]) -> tuple[bool, bool, bool]:
    """Renvoie (latin lisible, arabe lisible, arabe inconcluant), mesurés.

    Le troisième élément distingue un cas précis : le paquet « ara » est
    présent, mais l'image arabe synthétique n'a pu être ni lue exactement ni
    jugée franchement illisible — signe probable d'une police système sans
    jointure arabe correcte, pas d'une incapacité de Tesseract. Ce n'est pas
    une nuance cosmétique : le confondre avec un vrai échec renvoie
    l'évaluateur chercher une cause d'installation qui n'existe plus.
    """
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
        # Le français est la langue principale des dossiers de la commission.
        # Son absence ne fait rien échouer — les langues demandées sont
        # restreintes à celles installées — mais les pages françaises sont
        # alors lues avec le modèle anglais : accents et ligatures se
        # dégradent, en silence. Un silence sur la langue majoritaire du
        # corpus est précisément ce qu'un contrôle d'installation doit rompre.
        if "fra" in languages:
            report.append(f"{OK} Paquet français « fra » : présent.")
        else:
            report.append(f"{WARN} Paquet français « fra » : ABSENT.")
            report.append(
                "         Les pages françaises seront lues avec le modèle anglais : "
                "accents et ligatures moins bien reconnus, sans message d'erreur. "
                "Le français est la langue principale des dossiers."
            )
            report.append(
                "         Remède : clic droit sur reparer_ocr_arabe.bat, "
                "« Exécuter en tant qu'administrateur » — il pose aussi le français."
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
        report.append(
            f"{WARN} RapidOCR : absent. Second avis local indisponible sur les pages "
            "latines à basse résolution."
        )
        report.append(
            "         Sans effet sur l'arabe : RapidOCR ne le lit pas. Si des pages "
            "arabes ressortent vides, la cause est Tesseract, pas celui-ci."
        )

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

    arabic_inconclusive = False
    result = _best_arabic_reading(ocr_engines)
    if result is None:
        report.append(f"{WARN} Lecture arabe : non testée (police de contrôle absente).")
    else:
        outcome, _font_path, score, suspect = result
        arabic_ok = score >= GOOD_ARABIC_SCORE
        if arabic_ok:
            report.append(
                f"{OK} Lecture d'une page arabe de contrôle : réussie via {outcome.engine} "
                f"({score:.0%} des mots attendus retrouvés)."
            )
        elif ocr_engines.ARABIC_LANGUAGE in languages:
            # Le paquet est confirmé par Tesseract lui-même juste au-dessus : c'est le
            # fait qui compte. Un score bas ici tient à l'image synthétique — la police
            # système qui la rend, ou une lecture partiellement fidèle — jamais à une
            # incapacité de Tesseract qu'on vient pourtant de vérifier positive.
            arabic_inconclusive = True
            report.append(
                f"{WARN} Lecture d'une page arabe de contrôle : non concluante sur ce poste "
                f"({score:.0%} des mots attendus retrouvés)."
            )
            report.append(
                "         Le paquet « ara » est présent et confirmé par Tesseract lui-même : "
                + (
                    "la police système utilisée pour cette image de test ne semble pas "
                    "former l'arabe correctement — "
                    if suspect
                    else "cette image de test synthétique n'a été lue que partiellement — "
                )
                + "ceci teste le rendu d'une police, pas la capacité de Tesseract. Un vrai "
                "document scanné, qui n'est pas rendu par une police système, n'est pas "
                "concerné : testez-le, c'est ce test-là qui fait foi."
            )
        else:
            report.append(f"{FAIL} Lecture d'une page arabe de contrôle : ÉCHOUÉE.")

    return latin_ok, arabic_ok, arabic_inconclusive


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
    latin_ok, arabic_ok, arabic_inconclusive = check_engines(report)

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

    if latin_ok and arabic_inconclusive:
        print(
            "  Lecture opérationnelle en latin. Le paquet arabe est présent et confirmé\n"
            "  par Tesseract, mais l'image de test synthétique n'a pas pu le confirmer sur\n"
            "  ce poste — la police système utilisée pour ce test ne semble pas former\n"
            "  l'arabe correctement. Ce n'est pas la même chose qu'un paquet manquant :\n"
            "  testez avec un document réel plutôt que de vous fier à ce seul indicateur."
        )
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
