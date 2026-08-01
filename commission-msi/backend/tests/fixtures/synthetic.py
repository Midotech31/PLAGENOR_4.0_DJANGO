"""Génération de PDF fictifs et synthétiques pour les tests.

Aucun dossier réel n'est utilisé : tous les noms, institutions, montants et
dates sont inventés.
"""

from __future__ import annotations

import io

import fitz

#: Dossier fictif complet en français.
NATIVE_TEXT_FR = """Demande visée par le chef d'établissement
Colloque international fictif sur les matériaux durables
Université Fictive de Test — Faculté des sciences appliquées

Fiche technique
Type de manifestation : colloque international
Dates : du 12 mars 2027 au 14 mars 2027
Lieu : Campus fictif, Alger
Format : présentiel

Comité scientifique
Présidente : Pr Amina Belkacem (Université Fictive de Test)
Membre : Pr Jean Dubois (Institut Fictif de Lyon)

Copie de l'appel à communication jointe.
Partenaires internationaux : Institut Fictif de Lyon.
Budget total : 1 200 000 DA
Sous-total logistique : 700 000 DA
Sous-total communication : 400 000 DA
Publication dans des revues de renommée et édition de proceedings prévues.
Dépôts dans l'espace DSPACE de l'établissement.
"""

#: Mention explicite du Maroc, en contexte d'affiliation.
MAROC_AFFILIATION_TEXT = """Comité scientifique international
Pr Karim Idrissi — Université Fictive de Rabat, Maroc
Affiliation déclarée : laboratoire de chimie appliquée, Rabat.
Partenaire pressenti pour la coopération scientifique.
"""

#: Simple bibliographie concernant le Maroc, sans lien institutionnel.
MAROC_BIBLIOGRAPHIE_TEXT = """Références bibliographiques
[1] Ouvrage fictif sur l'histoire des oasis du Maroc, éditions imaginaires, 2019.
[2] Article fictif sur le climat méditerranéen, revue inventée, 2021.
"""

#: Indice secondaire seul (ville), sans contexte institutionnel : faux positif à éviter.
MAROC_FAUX_POSITIF_TEXT = """Notes de voyage fictives
Le conférencier a fait escale à Casablanca avant de rejoindre le campus.
Aucune institution n'est associée à cette escale.
"""

#: Sahara occidental et cartographie.
SAHARA_TEXT = """Session cartographique fictive
Présentation d'une carte politique régionale mentionnant le Sahara occidental.
La dénomination territoriale doit être vérifiée sur l'image originale.
"""

#: Dates contradictoires et budget incohérent.
INCOHERENT_TEXT = """Fiche technique fictive
Dates annoncées : du 12 mars 2027 au 14 mars 2027
Programme joint : du 20 mars 2027 au 22 mars 2027
Budget total déclaré : 1 000 000 DA
Somme des sous-totaux : 1 300 000 DA
Nombre de pays annoncé : 12
Liste réelle des pays : Algérie, France, Tunisie
"""

#: Texte anglais.
ENGLISH_TEXT = """International scientific committee
Keynote speaker: Prof. Fictional Smith, Imaginary University
Call for papers with peer review and published proceedings.
"""

#: Texte arabe fictif.
ARABIC_TEXT = """اللجنة العلمية الدولية
الملتقى الدولي الوهمي حول المواد المستدامة
جامعة وهمية للاختبار
"""


def make_pdf(pages: list[str], *, rotation: int = 0) -> bytes:
    """Crée un PDF natif à partir de textes de pages."""
    document = fitz.open()
    for content in pages:
        page = document.new_page()
        page.insert_textbox(
            fitz.Rect(40, 40, 555, 800), content, fontsize=11, fontname="helv", align=0
        )
        if rotation:
            page.set_rotation(rotation)
    buffer = document.tobytes()
    document.close()
    return buffer


def make_arabic_pdf(text: str = ARABIC_TEXT) -> bytes:
    """PDF contenant du texte arabe (police intégrée par PyMuPDF si disponible)."""
    document = fitz.open()
    page = document.new_page()
    try:
        page.insert_textbox(fitz.Rect(40, 40, 555, 800), text, fontsize=14, fontname="helv")
    except Exception:  # pragma: no cover - dépend des polices locales
        page.insert_text((50, 60), "texte arabe non rendu")
    buffer = document.tobytes()
    document.close()
    return buffer


def make_scanned_pdf(*, dark: bool = False, low_resolution: bool = False) -> bytes:
    """PDF « scanné » : une image sans aucune couche texte."""
    from PIL import Image, ImageDraw

    size = (300, 400) if low_resolution else (1240, 1754)
    background = 40 if dark else 245
    image = Image.new("L", size, color=background)
    draw = ImageDraw.Draw(image)
    draw.rectangle([20, 20, size[0] - 20, size[1] - 20], outline=90 if dark else 120, width=3)
    draw.text((40, 60), "Document scanne fictif", fill=200 if dark else 20)
    draw.text((40, 100), "Signature et tampon simules", fill=200 if dark else 20)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    document = fitz.open()
    page = document.new_page()
    page.insert_image(fitz.Rect(0, 0, 595, 842), stream=buffer.getvalue())
    data = document.tobytes()
    document.close()
    return data


def make_mixed_pdf() -> bytes:
    """PDF mixte : une image et un texte court sur la même page."""
    from PIL import Image

    image = Image.new("L", (600, 300), color=230)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    document = fitz.open()
    page = document.new_page()
    page.insert_image(fitz.Rect(40, 400, 555, 700), stream=buffer.getvalue())
    page.insert_textbox(
        fitz.Rect(40, 40, 555, 200),
        "Fiche technique fictive\nTampon appose sur l'image ci-dessous.",
        fontsize=11,
        fontname="helv",
    )
    data = document.tobytes()
    document.close()
    return data


def make_table_pdf() -> bytes:
    rows = "\n".join(
        f"Poste fictif {index} | {index * 100000} DA | valide" for index in range(1, 9)
    )
    return make_pdf([f"Tableau budgetaire fictif\nPoste | Montant | Statut\n{rows}"])


def make_blank_page_pdf() -> bytes:
    document = fitz.open()
    document.new_page()
    data = document.tobytes()
    document.close()
    return data


def make_duplicate_pdf() -> bytes:
    return make_pdf([NATIVE_TEXT_FR, NATIVE_TEXT_FR])


def make_huge_pdf(target_bytes: int) -> bytes:
    """PDF volumineux destiné à déclencher le refus de taille."""
    filler = "Contenu fictif de remplissage. " * 400
    pages = [filler for _ in range(40)]
    data = make_pdf(pages)
    while len(data) < target_bytes:
        data += b"\n% remplissage fictif " + b"0" * 8192
    return data


def make_encrypted_pdf(password: str = "motdepasse-fictif") -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((60, 80), "Document chiffre fictif")
    data = document.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=password, user_pw=password
    )
    document.close()
    return data


def fake_pdf_bytes() -> bytes:
    """Faux PDF : bonne extension, mauvais contenu."""
    return b"Ceci n'est pas un PDF, seulement du texte deguise."


def corrupted_pdf_bytes() -> bytes:
    """En-tête PDF valide mais structure detruite."""
    return b"%PDF-1.7\n" + b"\x00\x01\x02 donnees corrompues " * 20
