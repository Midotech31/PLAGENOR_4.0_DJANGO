"""Ce qui manque à l'installation ne doit pas être imputé au document.

Un poste a refusé de lire une page arabe parfaitement nette. L'application
répondait « contenu illisible — vérification humaine obligatoire », ce qui était
faux : la page était lisible, c'est le poste qui n'avait aucun moteur capable de
l'arabe.

Deux mesures fondent ces tests, et elles sont reproductibles :

* Tesseract avec son paquet « ara » lit cette écriture à ~89 % de confiance ;
* **RapidOCR renvoie une chaîne vide sur la même image**, sans lever d'erreur.
  Ses modèles PP-OCR embarqués couvrent le latin et le chinois. Il compte donc
  comme « moteur disponible » tout en étant incapable de la page — et c'est
  précisément ce qui transformait un défaut d'installation en accusation portée
  contre le document.
"""

from __future__ import annotations

import io
import sys

import pytest

from app.services import ocr_engines, ocr_service

ARABIC_LINES = (
    "الجمهورية الجزائرية الديمقراطية الشعبية",
    "وزارة التعليم العالي و البحث العلمي",
    "الموضوع: طلب الموافقة لتنظيم ملتقى دولي",
)

FONT = "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"


def _arabic_page() -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("L", (1000, 320), 255)
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(FONT, 36)
    except OSError:  # pragma: no cover - police absente du poste
        pytest.skip("Police arabe de test absente.")
    for index, line in enumerate(ARABIC_LINES):
        draw.text((40, 25 + index * 90), line, fill=20, font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# --------------------------------------------------------------------------
# La mesure qui fonde tout le reste
# --------------------------------------------------------------------------


@pytest.mark.skipif(not ocr_engines.rapidocr_available(), reason="RapidOCR absent.")
def test_rapidocr_reads_nothing_of_arabic_and_that_is_not_an_error():
    """Le piège : un moteur disponible, sans erreur, et pourtant muet."""
    result = ocr_engines.rapidocr_engine(_arabic_page())

    assert result.available is True, "il ne signale aucune panne"
    # Il ne renvoie pas forcément le vide : mesuré, il produit « rmg » à 62 % de
    # confiance. Du bruit affirmé avec aplomb est pire qu'un silence.
    for line in ARABIC_LINES:
        assert line not in result.text
    from app.core.text import useful_char_count

    assert useful_char_count(result.text) < ocr_engines.MIN_USEFUL_CHARS


@pytest.mark.skipif(
    not ocr_service.is_available() or "ara" not in ocr_service.installed_languages(),
    reason="Paquet Tesseract « ara » absent.",
)
def test_tesseract_with_the_arabic_pack_reads_the_same_page():
    result = ocr_engines.tesseract_engine(_arabic_page())

    assert result.text.strip(), result.note
    assert ARABIC_LINES[0] in result.text, result.text


# --------------------------------------------------------------------------
# Ce que l'application déclare savoir lire
# --------------------------------------------------------------------------


def test_rapidocr_never_counts_as_an_arabic_reader():
    assert "arabe" not in ocr_engines.ENGINE_SCRIPTS["rapidocr"]


def test_the_remedies_listed_never_include_rapidocr():
    """Proposer RapidOCR pour lire l'arabe enverrait l'évaluateur dans un mur."""
    _capable, missing = ocr_engines.arabic_capable()

    assert all("rapidocr" not in item.lower() for item in missing), missing


def test_a_missing_arabic_pack_is_named_as_such(monkeypatch):
    monkeypatch.setattr(ocr_service, "is_available", lambda: True)
    monkeypatch.setattr(ocr_service, "installed_languages", lambda: ["eng", "fra"])

    capable, missing = ocr_engines.arabic_capable()

    assert capable is False
    assert any("ara" in item for item in missing), missing
    assert any("installé mais ne connaît pas l'arabe" in item for item in missing), missing


def test_an_absent_tesseract_is_distinguished_from_a_missing_pack(monkeypatch):
    """Les deux pannes n'ont pas le même remède : les confondre fait perdre du temps."""
    monkeypatch.setattr(ocr_service, "is_available", lambda: False)

    _capable, missing = ocr_engines.arabic_capable()

    assert any("seul moteur local qui lise l'arabe" in item for item in missing), missing


def test_the_diagnostic_says_plainly_that_rapidocr_ignores_arabic():
    report = ocr_engines.diagnostic()

    rapid = next(item for item in report["barreaux"] if item["moteur"] == "rapidocr")
    assert "ne lit pas l'arabe" in rapid["portee"].lower()
    assert "arabe" not in rapid["ecritures"]
    assert "arabe_lisible" in report
    assert isinstance(report["manque_pour_l_arabe"], list)


def test_the_diagnostic_lists_the_installed_tesseract_languages():
    report = ocr_engines.diagnostic()

    tesseract = next(item for item in report["barreaux"] if item["moteur"] == "tesseract")
    assert isinstance(tesseract["langues"], list)
    if tesseract["disponible"]:
        assert tesseract["langues"], "un moteur présent doit dire ce qu'il connaît"


# --------------------------------------------------------------------------
# Le message rendu à l'évaluateur
# --------------------------------------------------------------------------


def test_an_unreadable_page_blames_the_installation_not_the_document(monkeypatch):
    """Le défaut central : accuser la page d'un manque qui est celui du poste."""
    monkeypatch.setattr(ocr_service, "is_available", lambda: False)
    monkeypatch.setattr(ocr_engines, "rapidocr_available", lambda: False)

    outcome = ocr_engines.read_page(b"")

    assert outcome.engine == "aucun"
    assert "ne sait lire l'arabe" in outcome.notice
    assert "ce n'est pas elle qui est illisible" in outcome.notice
    assert "RapidOCR ne comble pas ce manque" in outcome.notice


def test_three_characters_of_noise_do_not_hide_the_missing_pack(monkeypatch):
    """Le cas réel : « rmg » à 62 % suffisait à masquer la cause véritable."""
    monkeypatch.setattr(ocr_service, "is_available", lambda: False)
    monkeypatch.setattr(ocr_engines, "rapidocr_available", lambda: True)
    noisy = lambda *a, **k: ocr_engines.EngineResult(  # noqa: E731
        engine="rapidocr", text="rmg", confidence=61.95, quality=0.4344
    )
    monkeypatch.setattr(ocr_engines, "LADDER", (("rapidocr", noisy),))

    outcome = ocr_engines.read_page(b"")

    assert outcome.text == "rmg"
    assert outcome.human_transcription_required is True
    assert "moins de 40 caractères utiles" in outcome.notice
    assert "ne sait lire l'arabe" in outcome.notice, outcome.notice


def test_when_arabic_is_readable_the_message_stays_about_the_page(monkeypatch):
    """Si le poste sait lire l'arabe, une page vide est bien un problème de page."""
    monkeypatch.setattr(ocr_service, "is_available", lambda: True)
    monkeypatch.setattr(ocr_service, "installed_languages", lambda: ["ara", "fra"])
    monkeypatch.setattr(ocr_service, "run_ocr", lambda *a, **k: _empty_result())

    outcome = ocr_engines.read_page(b"")

    assert outcome.notice == ocr_engines.HUMAN_TRANSCRIPTION_REQUIRED


def _empty_result():
    from app.services.ocr_service import OcrResult

    return OcrResult(
        text="",
        confidence=None,
        words=[],
        languages="ara+fra",
        engine_version="test",
        parameters={},
    )


def test_the_diagnostic_is_reachable_without_a_terminal(client):
    response = client.get("/api/v1/diagnostic-ocr")

    assert response.status_code == 200
    payload = response.json()
    assert "barreaux" in payload
    assert "arabe_lisible" in payload


# --------------------------------------------------------------------------
# Vérification d'installation
# --------------------------------------------------------------------------


def _verify_module():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "verify_install.py"
    spec = importlib.util.spec_from_file_location("verify_install", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_path_budget_matches_the_failure_that_produced_it():
    """Le chemin réel qui a échoué faisait 133 caractères ; le budget doit le refuser.

    L'installation avait échoué sur un fichier d'`onnxruntime` à 262 caractères,
    deux de trop. Le budget se déduit de cette mesure, il n'est pas choisi au
    hasard : 260 moins la profondeur observée des dépendances, moins une marge.
    """
    verify = _verify_module()

    budget = verify.MAX_PATH - verify.DEEPEST_DEPENDENCY_SUFFIX - verify.PATH_SAFETY_MARGIN
    assert budget < 133, "le chemin qui a réellement échoué doit être refusé"
    assert budget > 60, "un budget trop strict refuserait des chemins acceptables"


def test_a_too_long_path_names_both_remedies(tmp_path, monkeypatch):
    verify = _verify_module()
    monkeypatch.setattr(verify, "ROOT", tmp_path / ("x" * 140))

    report: list[str] = []
    assert verify.check_path_length(report) is False

    text = " ".join(report)
    assert "260" in text
    assert "C:\\CommissionMSI" in text
    assert "LongPathsEnabled" in text


def test_a_short_path_passes_without_noise(tmp_path, monkeypatch):
    verify = _verify_module()
    monkeypatch.setattr(verify, "ROOT", tmp_path)

    report: list[str] = []
    assert verify.check_path_length(report) is True
    assert len(report) == 1, "un chemin correct ne mérite pas cinq lignes d'explication"


def test_the_verdict_distinguishes_no_reading_from_no_arabic():
    """« Rien n'est lu » et « l'arabe n'est pas lu » n'appellent pas la même action."""
    verify = _verify_module()
    import inspect

    source = inspect.getsource(verify.main)
    assert "PAS les pages arabes" in source
    assert "AUCUNE page scannée" in source


def test_the_verdict_also_distinguishes_inconclusive_from_definitively_unreadable():
    """Un test synthétique raté par la police système n'est pas un paquet absent."""
    verify = _verify_module()
    import inspect

    source = inspect.getsource(verify.main)
    assert "arabic_inconclusive" in source
    assert "n'est pas la même chose qu'un paquet manquant" in source


# --------------------------------------------------------------------------
# Un rendu arabe raté par la police système n'est pas un vrai échec
# --------------------------------------------------------------------------


def test_a_correct_rendering_is_never_flagged_as_garbled():
    verify = _verify_module()

    correct = (
        "الجمهورية الجزائرية الديمقراطية الشعبية\n"
        "وزارة التعليم العالي و البحث العلمي\n"
        "الموضوع: طلب الموافقة لتنظيم ملتقى دولي"
    )
    assert verify._looks_garbled(correct) is False


def test_a_font_without_arabic_joining_is_flagged_as_garbled():
    """Mesuré : une police sans jointure arabe correcte répète « لا » pour la

    moitié des paires de lettres lues, contre 11 % sur un rendu correct.
    """
    verify = _verify_module()

    garbled = "الالالالالالالا لالالالالالالالالا لالالالالالالالالالالا"
    assert verify._looks_garbled(garbled) is True


def test_a_font_with_almost_no_arabic_glyph_is_flagged_as_garbled():
    """Mesuré : une police sans glyphes arabes du tout ne produit presque

    aucune lettre arabe en sortie, pas du texte arabe faux.
    """
    verify = _verify_module()

    assert verify._looks_garbled("0000000000\n00000\n0 0\n0ن 0\n0 0\n00600") is True


def test_windows_arabic_shaping_fonts_are_tried_before_the_less_reliable_ones():
    """Tahoma et Segoe UI, historiquement chargés de l'arabe sur Windows,

    doivent être essayés avant Arial et Times New Roman.
    """
    verify = _verify_module()
    fonts = [font.lower() for font in verify.ARABIC_FONTS]

    tahoma = next(i for i, f in enumerate(fonts) if "tahoma" in f)
    segoe = next(i for i, f in enumerate(fonts) if "segoeui" in f)
    arial = next(i for i, f in enumerate(fonts) if f.endswith("arial.ttf"))
    times = next(i for i, f in enumerate(fonts) if "times" in f)

    assert tahoma < arial
    assert segoe < arial
    assert tahoma < times
    assert segoe < times


def test_a_garbling_font_reports_inconclusive_not_failed_when_the_pack_is_present():
    """Reproduit la mesure réelle : le paquet arabe installé, la seule police

    disponible sur ce poste réel n'articule pas l'arabe correctement.
    """
    verify = _verify_module()
    verify.ARABIC_FONTS = (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    )

    report: list[str] = []
    _latin_ok, arabic_ok, inconclusive = verify.check_engines(report)

    assert arabic_ok is False
    assert inconclusive is True
    assert any("non concluante" in line for line in report)
    assert any("n'est pas concerné" in line for line in report)


# --------------------------------------------------------------------------
# Une variante de graphie usuelle n'est pas un échec de lecture
# --------------------------------------------------------------------------
#
# Le défaut réel, trouvé sur un poste où le paquet arabe était installé et
# confirmé par Tesseract : le contrôle comparait le texte lu **brut** à la
# ligne attendue par inclusion littérale, sans jamais appeler la
# normalisation du reste de l'application. Une variante de graphie usuelle —
# alif maksoura pour ya, un ligature différente — suffisait à faire échouer
# une lecture par ailleurs correcte, et le message affirmait « ÉCHOUÉE » là où
# le paquet fonctionnait.


def test_a_common_spelling_variant_still_scores_as_a_good_reading():
    """Mesuré : Tesseract lit « العالى » (alif maksoura) là où l'image porte

    « العالي » (ya) — une variante usuelle, pas une erreur de lecture. Le
    score doit rester au-dessus du seuil de bonne lecture.
    """
    verify = _verify_module()

    read_with_variant = (
        "الجمهورية الجزائرية الديمقراطية الشعبية\n"
        "وزارة التعليم العالى و البحث العلمى\n"
        "الموضوع: طلب الموافقة لتنظيم ملتقى دولي"
    )
    score = verify._reading_score(read_with_variant)

    assert score >= verify.GOOD_ARABIC_SCORE, score


def test_the_previous_check_would_have_wrongly_failed_this_same_text():
    """Verrouille le défaut lui-même : l'ancienne comparaison littérale

    aurait échoué sur ce texte, bien que la lecture soit correcte.
    """
    read_with_variant = (
        "وزارة التعليم العالى و البحث العلمى"  # ى (alif maksoura), pas ي (ya)
    )
    expected_line = "وزارة التعليم العالي و البحث العلمي"  # ي (ya)

    assert expected_line not in read_with_variant, (
        "si ce texte redevenait identique, le test ne prouverait plus rien"
    )


def test_garbled_text_still_scores_far_below_the_threshold():
    verify = _verify_module()

    garbled = "الالالالالالالا لالالالالالالالالا لالالالالالالالالالالا"
    assert verify._reading_score(garbled) < verify.GOOD_ARABIC_SCORE


def test_once_the_pack_is_confirmed_the_verdict_is_never_a_hard_failure(monkeypatch):
    """Le fait qui compte : Tesseract confirme « ara ». Un score bas ensuite

    ne doit jamais reproduire le faux « ÉCHOUÉE » mesuré en usage réel.
    """
    verify = _verify_module()
    from app.services import ocr_engines, ocr_service

    monkeypatch.setattr(ocr_service, "is_available", lambda: True)
    monkeypatch.setattr(ocr_service, "installed_languages", lambda: ["ara", "eng", "osd"])
    monkeypatch.setattr(verify, "_best_arabic_reading", lambda _engines: (
        type("Outcome", (), {"engine": "tesseract", "text": "quelque chose de partiel"})(),
        "police-de-test",
        0.2,  # score bas, mais le paquet est confirmé au-dessus
        False,
    ))

    report: list[str] = []
    _latin_ok, arabic_ok, inconclusive = verify.check_engines(report)

    assert arabic_ok is False
    assert inconclusive is True, "jamais un échec dur quand Tesseract confirme le paquet"
    assert not any("ÉCHOUÉE" in line for line in report)


# --------------------------------------------------------------------------
# Trouver Tesseract même hors du PATH
# --------------------------------------------------------------------------


def test_tesseract_is_found_at_its_default_windows_location(tmp_path, monkeypatch):
    """L'installateur Windows n'ajoute pas Tesseract au PATH par défaut.

    Sans cette recherche, un moteur parfaitement installé était déclaré absent,
    et l'évaluateur repartait réinstaller ce qu'il avait déjà.
    """
    fake = tmp_path / "Tesseract-OCR" / "tesseract.exe"
    fake.parent.mkdir(parents=True)
    fake.write_bytes(b"")

    monkeypatch.setattr(ocr_service.shutil, "which", lambda _name: None)
    monkeypatch.setattr(ocr_service, "WINDOWS_DEFAULT_PATHS", (str(fake),))

    assert ocr_service.tesseract_command() == str(fake)
    assert ocr_service.is_available() is True


def test_a_user_installation_without_admin_rights_is_found(tmp_path, monkeypatch):
    base = tmp_path / "AppData"
    fake = base / "Programs" / "Tesseract-OCR" / "tesseract.exe"
    fake.parent.mkdir(parents=True)
    fake.write_bytes(b"")

    monkeypatch.setattr(ocr_service.shutil, "which", lambda _name: None)
    monkeypatch.setattr(ocr_service, "WINDOWS_DEFAULT_PATHS", ())
    monkeypatch.setenv("LOCALAPPDATA", str(base))

    assert ocr_service.tesseract_command() == str(fake)


def test_an_explicit_configuration_always_wins(tmp_path, monkeypatch):
    """L'évaluateur doit pouvoir imposer une version précise."""
    chosen = tmp_path / "choisi.exe"
    chosen.write_bytes(b"")
    other = tmp_path / "autre.exe"
    other.write_bytes(b"")

    from app.core.config import get_settings, reset_settings

    monkeypatch.setenv("MSI_TESSERACT_CMD", str(chosen))
    reset_settings()
    try:
        monkeypatch.setattr(ocr_service.shutil, "which", lambda _name: str(other))
        assert ocr_service.tesseract_command() == str(chosen)
    finally:
        monkeypatch.delenv("MSI_TESSERACT_CMD", raising=False)
        reset_settings()
    assert get_settings() is not None


def test_nothing_installed_stays_honestly_absent(monkeypatch):
    monkeypatch.setattr(ocr_service.shutil, "which", lambda _name: None)
    monkeypatch.setattr(ocr_service, "WINDOWS_DEFAULT_PATHS", ())
    monkeypatch.setattr(ocr_service, "_windows_candidates", list)

    assert ocr_service.tesseract_command() is None
    assert ocr_service.is_available() is False


# --------------------------------------------------------------------------
# Installation automatique du paquet arabe
# --------------------------------------------------------------------------


def _installer_module():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "installer_arabe.py"
    spec = importlib.util.spec_from_file_location("installer_arabe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_tessdata_directory_is_read_from_tesseract_not_guessed():
    """Deviner le dossier à partir du binaire est faux dès que TESSDATA_PREFIX existe."""
    installer = _installer_module()

    line = 'List of available languages in "/usr/share/tesseract-ocr/5/tessdata/" (4):'
    assert installer.TESSDATA_LINE.search(line).group(1) == (
        "/usr/share/tesseract-ocr/5/tessdata/"
    )


def test_an_error_page_is_never_installed_as_a_model(monkeypatch):
    """Une page d'erreur de quelques centaines d'octets ne doit pas devenir un modèle."""
    installer = _installer_module()

    class _Tiny:
        def read(self):
            return b"<html>403 Forbidden</html>"

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(installer.urllib.request, "urlopen", lambda *a, **k: _Tiny())

    assert installer._fetch() is None


def test_a_refused_mirror_falls_back_to_the_next(monkeypatch):
    """Une seule adresse serait un point de rupture unique — mesuré en 403."""
    installer = _installer_module()
    seen: list[str] = []

    class _Payload:
        def __init__(self, data):
            self.data = data

        def read(self):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def _open(url, *_args, **_kwargs):
        seen.append(url)
        if len(seen) == 1:
            raise OSError("HTTP Error 403: Forbidden")
        return _Payload(b"x" * (installer.MIN_MODEL_BYTES + 1))

    monkeypatch.setattr(installer.urllib.request, "urlopen", _open)

    payload = installer._fetch()
    assert payload is not None
    assert len(seen) == 2, "la seconde adresse doit être essayée"


def test_the_mirrors_do_not_all_share_the_same_host():
    """Trois adresses sur un seul hôte ne protègent de rien."""
    installer = _installer_module()
    from urllib.parse import urlparse

    hosts = {urlparse(url).netloc for url in installer.ARABIC_MODEL_URLS}
    assert len(hosts) >= 2, hosts


def test_an_installed_file_is_confirmed_by_asking_tesseract(monkeypatch, tmp_path):
    """Le fichier posé ne prouve rien : seul Tesseract dit ce qu'il sait lire."""
    installer = _installer_module()
    monkeypatch.setattr(installer, "_download", lambda _target, _lang="ara": True)
    monkeypatch.setattr(installer, "_languages", lambda _cmd: (["eng", "fra"], None))

    assert installer._install_arabic("tesseract", str(tmp_path)) is False


def test_french_is_installed_alongside_arabic_when_both_are_missing():
    """Mesuré sur un poste réel : winget ne pose que l'anglais et osd.

    Les dossiers de la commission sont bilingues français/arabe ; installer
    l'un sans l'autre laisserait la moitié du dossier illisible.
    """
    installer = _installer_module()

    assert set(installer.REQUIRED_LANGUAGES) == {"ara", "fra"}
    assert installer.LANGUAGE_LABELS["ara"] == "arabe"
    assert installer.LANGUAGE_LABELS["fra"] == "français"


def test_missing_languages_are_each_installed_and_reverified(monkeypatch):
    """Les deux paquets manquants doivent chacun être posés puis reconfirmés."""
    installer = _installer_module()
    attempted: list[str] = []

    monkeypatch.setattr(installer, "_tesseract", lambda: "tesseract")
    monkeypatch.setattr(installer, "_languages", lambda _cmd: (["eng", "osd"], "/tessdata"))

    def _install(_command, _tessdata, lang):
        attempted.append(lang)
        return True

    monkeypatch.setattr(installer, "_install_language", _install)

    class _Stub:
        @staticmethod
        def check_engines(_report):
            return True, True, False

    monkeypatch.setitem(sys.modules, "verify_install", _Stub())
    assert installer.main() == 0
    assert set(attempted) == {"ara", "fra"}


def test_an_inconclusive_arabic_test_is_not_reported_as_a_failure(monkeypatch):
    """Le paquet est confirmé par Tesseract : ne pas renvoyer l'utilisateur

    chercher une cause d'installation qui n'existe plus.
    """
    installer = _installer_module()

    monkeypatch.setattr(installer, "_tesseract", lambda: "tesseract")
    monkeypatch.setattr(installer, "_languages", lambda _cmd: (["ara", "fra", "eng"], "/tessdata"))

    class _Stub:
        @staticmethod
        def check_engines(_report):
            return True, False, True  # latin ok, arabe non confirmé, inconcluant

    monkeypatch.setitem(sys.modules, "verify_install", _Stub())
    assert installer.main() == 0


def test_the_winget_identifier_is_the_one_observed_on_a_real_machine():
    """Un identifiant supposé enverrait l'utilisateur sur une commande fausse."""
    installer = _installer_module()

    assert installer.WINGET_PACKAGE == "UB-Mannheim.TesseractOCR"


def test_a_double_clickable_repair_exists_and_relocates_itself():
    """Un chemin relatif tapé depuis un autre dossier ne donne qu'une erreur muette."""
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "reparer_ocr_arabe.bat"
    assert script.is_file(), "le raccourci de réparation doit être livré"

    content = script.read_text(encoding="utf-8", errors="ignore")
    # Sans cette ligne, le fichier ne marche que depuis le bon dossier.
    assert 'cd /d "%~dp0"' in content
    assert "installer_arabe.py" in content
    # Une fenêtre qui se referme aussitôt ne montre aucun message.
    assert "pause" in content


def test_the_repair_shortcut_self_elevates_when_writing_needs_admin_rights():
    """winget installe Tesseract dans Program Files : y écrire exige l'administrateur.

    Mesuré sur un poste réel : Tesseract trouvé, paquet arabe absent, puis
    « Permission denied » à l'écriture dans Program Files\\Tesseract-OCR\\tessdata.
    Le raccourci doit demander l'élévation lui-même plutôt que de renvoyer
    l'utilisateur relancer à la main.
    """
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "reparer_ocr_arabe.bat"
    content = script.read_text(encoding="utf-8", errors="ignore")

    assert "net session" in content, "détection des droits administrateur absente"
    assert "-Verb RunAs" in content, "pas de demande d'élévation"
    assert "Start-Process" in content
    # Un marqueur en argument évite de redemander l'élévation en boucle si
    # elle échoue ou si l'utilisateur la refuse.
    assert "ELEVE" in content


def test_the_repair_shortcut_is_shipped_in_the_archive():
    """Un outil de dépannage absent de l'archive ne dépanne personne."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "build_archive.py"
    spec = importlib.util.spec_from_file_location("build_archive", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert "reparer_ocr_arabe.bat" in module.ROOT_FILES
