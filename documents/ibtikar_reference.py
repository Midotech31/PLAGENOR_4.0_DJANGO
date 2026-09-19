"""Source-preservation helpers for official IBTIKAR forms."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import re

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn

_TEMPLATE_DIR = Path(__file__).resolve().parent / "docx_templates" / "ibtikar"
_TEMPLATE_MAP = {
    "EGTP-SeqS": "egtp_seqs.docx",
    "EGTP-Seq02": "egtp_seq02.docx",
    "EGTP-PCR": "egtp_pcr.docx",
    "EGTP-GDE": "egtp_gde.docx",
    "EGTP-CAN": "egtp_can.docx",
    "EGTP-PS": "egtp_ps.docx",
    "EGTP-IMT": "egtp_imt.docx",
    "EGTP-Illumina-Microbial-WGS": "egtp_illumina_wgs.docx",
    "EGTP-Lyoph": "egtp_lyoph.docx",
}

_DYNAMIC_PREFIXES = {
    "EGTP-SeqS": (
        "4. type d’échantillon soumis", "4. type d'échantillon soumis",
        "5. informations supplémentaires", "sens de lecture souhaité",
        "kit d’amplification", "résultats du contrôle de qualité",
    ),
    "EGTP-Seq02": (
        "4. informations supplémentaires", "méthode d’extraction souhaitée",
        "type de kit de pcr", "techniques de contrôle qualité",
        "marqueur de taille", "sens de lecture souhaité",
    ),
    "EGTP-PCR": (
        "4. informations supplémentaires", "type de kit pcr",
        "techniques de contrôle qualité", "marqueur de taille",
        "veuillez indiquer le volume",
    ),
    "EGTP-GDE": (
        "4. informations supplémentaires", "méthode d’extraction souhaitée",
        "techniques de contrôle qualité", "volume d’adn souhaité",
    ),
    "EGTP-CAN": (
        "4. informations supplémentaires", "techniques de contrôle qualité souhaitées",
        "pourcentage de gel", "marqueur de taille",
    ),
    "EGTP-PS": (
        "4. informations supplémentaires", "veuillez sélectionner l’état physique",
        "veuillez indiquer le volume final",
    ),
    "EGTP-IMT": (
        "4. informations supplémentaires", "fourniture de cultures fraîches",
        "type de cible souhaitée", "mode d’analyse",
    ),
}

_SOURCE_CORRECTIONS = {
    "EGTP-Lyoph": {"Alpha 3-4 LSCbasic": "Beta 2-8 LSCplus"},
}

def _norm(value):
    value = (value or "").replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", value)

def _is_dynamic_prompt(service_code, text):
    lower = _norm(text).casefold()
    if not lower:
        return True
    if "cliquez ou appuyez ici" in lower or "choisissez un élément" in lower:
        return True
    if "☐" in text:
        return True
    return any(lower.startswith(prefix.casefold()) for prefix in _DYNAMIC_PREFIXES.get(service_code, ()))

def _correct(service_code, text):
    value = _norm(text)
    for old, new in _SOURCE_CORRECTIONS.get(service_code, {}).items():
        value = value.replace(old, new)
    return value

def _iter_blocks(document):
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)

def _table_rows(table):
    return [[_norm(cell.text) for cell in row.cells] for row in table.rows]

def extract_reference_content(service_code):
    """Return useful fixed source content, excluding variable input prompts."""
    name = _TEMPLATE_MAP.get(service_code)
    if not name:
        return {"guidance": [], "tables": [], "blocks": [], "ethics": ""}
    path = _TEMPLATE_DIR / name
    if not path.exists():
        return {"guidance": [], "tables": [], "blocks": [], "ethics": ""}
    document = Document(path)
    sample_table_seen = False
    collecting = False
    guidance, tables, blocks = [], [], []
    ethics = ""
    ethical_next = False
    for block in _iter_blocks(document):
        if isinstance(block, Table):
            rows = _table_rows(block)
            header = " ".join(rows[0]).casefold() if rows else ""
            if not sample_table_seen and ("code" in header or "séquence" in header or "échantillon" in header):
                sample_table_seen = True
                collecting = True
                continue
            if collecting and rows:
                if any("validation de la demande" in " ".join(row).casefold() for row in rows):
                    break
                tables.append(rows)
                blocks.append({"type": "table", "rows": rows})
            continue
        text = _correct(service_code, block.text)
        low = text.casefold()
        if not sample_table_seen:
            continue
        if "validation de la demande" in low or low.startswith("administration de plagenor"):
            break
        if low.startswith("déclaration de responsabilité éthique"):
            ethical_next = True
            continue
        if ethical_next:
            if text and not text.startswith("Signature du demandeur"):
                ethics = text
                ethical_next = False
                continue
            ethical_next = False
        if not collecting or not text:
            continue
        if text.startswith("Signature du demandeur"):
            continue
        if _is_dynamic_prompt(service_code, text):
            continue
        guidance.append(text)
        blocks.append({"type": "paragraph", "text": text})
    return {"guidance": guidance, "tables": tables, "blocks": blocks, "ethics": ethics}

_EXTRA = {
    "EGTP-SeqS": {
        "guidance": [
            "Acknowledgment and Citation Clause",
            "This research was conducted at the Genomics Technology Platform of the Higher School of Biological Sciences of Oran. We gratefully acknowledge the support and contributions of the platform staff for their assistance in data analysis and interpretation.",
            "Additionally, please ensure that any substantial contributions by platform staff are recognized in accordance with standard authorship guidelines.",
        ],
    },
    "EGTP-PSM": {
        "guidance": [
            "Échantillons pathogènes ou d'origine clinique",
            "Pour tout échantillon pathogène ou d'origine clinique, le demandeur doit joindre un document de déclaration de risque biologique précisant au minimum le niveau de biosécurité requis (ex. : classe 2 ou 3), conformément à la directive 2000/54/CE et aux normes ISO 35001.",
            "En l'absence de ce document, la demande sera systématiquement suspendue ou refusée, conformément aux normes de biosécurité et de transport des substances infectieuses (ADR 6.2, IATA DGR).",
            "Il est strictement interdit d'envoyer des échantillons présentant un risque non déclaré.",
            "Mode de livraison et présentation des échantillons",
            "Les échantillons doivent être exclusivement apportés par le demandeur à la plateforme PLAGENOR, accompagnés de la fiche IBTIKAR dûment renseignée et signée.",
            "Aucun autre mode de livraison (transport postal, courrier spécialisé, etc.) ne sera accepté.",
            "Conditions thermiques lors de la livraison",
            "Les conditions thermiques suivantes s'appliquent à TOUS les échantillons, qu'ils soient ordinaires ou à risque biologique.",
            "Échantillons non congelés (liquides ou suspensions) : température 2–8 °C ; contenant isotherme avec éléments réfrigérants ; délai maximal 24 heures ; confirmer l'état du récipient à la réception.",
            "Échantillons congelés (−20 °C / −80 °C) : température ≤ −20 °C, idéalement −80 °C ; transport adapté, notamment glace carbonique lorsque nécessaire ; conditionnement conforme.",
            "Échantillons déjà lyophilisés : température ambiante (15–25 °C) ou réfrigérée (2–8 °C) selon stabilité ; récipient hermétique protégé de l'humidité et de la lumière.",
        ],
        "ethics": "La signature de ce formulaire atteste que les échantillons soumis ont été collectés, manipulés et transférés conformément aux normes éthiques et réglementaires en vigueur. Le demandeur en assume l'entière responsabilité quant à la nature, l'origine et l'utilisation des échantillons, y compris toute implication éthique ou juridique liée à leur traitement ou analyse.",
    },
}

def reference_content(service_code):
    base = extract_reference_content(service_code)
    extra = _EXTRA.get(service_code, {})
    if extra.get("guidance"):
        base["guidance"].extend(extra["guidance"])
        base.setdefault("blocks", []).extend(
            {"type": "paragraph", "text": value} for value in extra["guidance"]
        )
    if extra.get("ethics"):
        base["ethics"] = extra["ethics"]
    return deepcopy(base)
