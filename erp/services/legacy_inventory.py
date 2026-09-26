from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import unicodedata
import uuid
import zipfile
from defusedxml import ElementTree as ET

from django.core.exceptions import ValidationError
from django.db import transaction

SOURCE_XLSX = "Inventaire PLAGENOR2026.xlsx"
SOURCE_ZIP = "Inventaire - PLAGENOR-20260925T161439Z-1-001.zip"
BASELINE_DATE = date(2026, 9, 25)
SCHEMA_VERSION = 1

_XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOCX_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_hash(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _norm(value) -> str:
    text = unicodedata.normalize("NFKC", _text(value)).casefold()
    text = " ".join(text.split())
    return re.sub(r"[^0-9a-zà-ÿ]+", " ", text).strip()


def _slug(value, fallback="X") -> str:
    text = unicodedata.normalize("NFKD", _text(value)).encode("ascii", "ignore").decode().upper()
    text = re.sub(r"[^A-Z0-9]+", "-", text).strip("-")
    return text or fallback


def _source_key(prefix, *parts) -> str:
    safe = ":".join(_text(part) for part in parts)
    digest = hashlib.sha256((prefix + ":" + safe).encode("utf-8")).hexdigest()[:20]
    return f"INV26:{prefix}:{digest}"


def _source_record_payload(source_file, source_section, source_row, kind, raw):
    return {
        "source_file": source_file,
        "source_section": source_section,
        "source_row": str(source_row or ""),
        "kind": kind,
        "raw_data": raw,
        "fingerprint": _canonical_hash(raw),
    }


def _column_number(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref or "")
    if not match:
        return 0
    value = 0
    for char in match.group(1):
        value = value * 26 + ord(char) - 64
    return value


def _xlsx_cell_value(cell, shared):
    ns = f"{{{_XLSX_NS}}}"
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(ns + "t"))
    value = cell.find(ns + "v")
    raw = "" if value is None else value.text or ""
    if cell_type == "s" and raw:
        return shared[int(raw)]
    if cell_type == "b":
        return "TRUE" if raw == "1" else "FALSE"
    return raw


def _xlsx_sheets(data: bytes):
    ns = f"{{{_XLSX_NS}}}"
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.text or "" for node in item.iter(ns + "t")) for item in root]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rel_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relations = {node.attrib["Id"]: node.attrib["Target"] for node in rel_root}
        sheets = {}
        for sheet in workbook.find(ns + "sheets"):
            relation = sheet.attrib[f"{{{_OFFICE_REL_NS}}}id"]
            target = relations[relation].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            root = ET.fromstring(archive.read(target))
            matrix = []
            sheet_data = root.find(ns + "sheetData")
            if sheet_data is None:
                sheets[sheet.attrib["name"]] = []
                continue
            for row in sheet_data:
                row_no = int(row.attrib.get("r", len(matrix) + 1))
                values = {}
                max_col = 0
                for cell in row.findall(ns + "c"):
                    column = _column_number(cell.attrib.get("r", ""))
                    max_col = max(max_col, column)
                    values[column] = _xlsx_cell_value(cell, shared)
                matrix.append((row_no, [values.get(index, "") for index in range(1, max_col + 1)]))
            sheets[sheet.attrib["name"]] = matrix
        return sheets


def _records_from_sheet(matrix):
    usable = [(row_no, values) for row_no, values in matrix if any(_text(value) for value in values)]
    if not usable:
        return []
    _, header_values = usable[0]
    headers = []
    seen = Counter()
    for index, value in enumerate(header_values, 1):
        label = _text(value) or f"Colonne{index}"
        seen[label] += 1
        if seen[label] > 1:
            label = f"{label}_{seen[label]}"
        headers.append(label)
    records = []
    for row_no, values in usable[1:]:
        padded = values + [""] * max(0, len(headers) - len(values))
        raw = {headers[index]: padded[index] for index in range(len(headers))}
        if any(_text(value) for value in raw.values()):
            raw["__row__"] = row_no
            records.append(raw)
    return records


def _docx_tables(data: bytes):
    ns = f"{{{_DOCX_NS}}}"
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    for table in root.iter(ns + "tbl"):
        rows = []
        for row in table.findall(ns + "tr"):
            cells = []
            for cell in row.findall(ns + "tc"):
                paragraphs = []
                for paragraph in cell.iter(ns + "p"):
                    text = "".join(node.text or "" for node in paragraph.iter(ns + "t"))
                    if text:
                        paragraphs.append(text)
                cells.append("\n".join(paragraphs).strip())
            rows.append(cells)
        yield rows


def _equipment_rows_from_zip(data: bytes):
    result = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in sorted(archive.namelist()):
            if not member.lower().endswith(".docx") or member.startswith("__MACOSX/"):
                continue
            filename = PurePosixPath(member).name
            room_match = re.search(r"(\d{1,2})(?=\.docx$)", filename, flags=re.I)
            room = room_match.group(1).zfill(2) if room_match else ""
            for table in _docx_tables(archive.read(member)):
                if not table:
                    continue
                header_index = next(
                    (index for index, row in enumerate(table)
                     if any("equipment name" in _norm(cell) for cell in row)),
                    None,
                )
                if header_index is None:
                    continue
                headers = [cell.strip() or f"Column{idx + 1}" for idx, cell in enumerate(table[header_index])]
                for row_index, values in enumerate(table[header_index + 1:], header_index + 2):
                    padded = values + [""] * max(0, len(headers) - len(values))
                    raw = {headers[index]: padded[index] for index in range(len(headers))}
                    if not any(_text(value) for value in raw.values()):
                        continue
                    if not any(_text(raw.get(key)) for key in (
                        "Equipment Name", "Model", "Reference", "Serial Number (S/N)"
                    )):
                        continue
                    raw.update({
                        "__source_file__": filename,
                        "__source_row__": row_index,
                        "__room__": room,
                    })
                    result.append(raw)
    return result


def parse_inventory_sources(xlsx_path, zip_path):
    xlsx_path, zip_path = Path(xlsx_path), Path(zip_path)
    xlsx_data, zip_data = xlsx_path.read_bytes(), zip_path.read_bytes()
    sheets = {name: _records_from_sheet(matrix) for name, matrix in _xlsx_sheets(xlsx_data).items()}
    equipment = _equipment_rows_from_zip(zip_data)
    return {
        "schema": SCHEMA_VERSION,
        "source": {
            "xlsx": {"name": xlsx_path.name, "sha256": _sha256_bytes(xlsx_data)},
            "zip": {"name": zip_path.name, "sha256": _sha256_bytes(zip_data)},
            "baseline_date": BASELINE_DATE.isoformat(),
        },
        "sheets": sheets,
        "equipment_room_inventory": equipment,
    }


def write_manifest_gz(manifest, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with gzip.GzipFile(filename="", mode="wb", fileobj=path.open("wb"), mtime=0) as stream:
        stream.write(raw)
    return path


def load_manifest_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        manifest = json.load(stream)
    if manifest.get("schema") != SCHEMA_VERSION:
        raise ValidationError("Version de manifeste d’inventaire non prise en charge.")
    return manifest


def _sheet(manifest, needle):
    wanted = _norm(needle)
    for name, rows in manifest.get("sheets", {}).items():
        if wanted in _norm(name):
            return name, rows
    return needle, []


def _field(row, *names):
    lookup = {_norm(key): value for key, value in row.items() if not key.startswith("__")}
    for name in names:
        if _norm(name) in lookup:
            return lookup[_norm(name)]
    return ""


def _integer(value):
    try:
        number = Decimal(_text(value).replace(",", "."))
    except InvalidOperation:
        return None
    if number < 0 or number != number.to_integral_value():
        return None
    return int(number)


def _decimal(value):
    try:
        return Decimal(_text(value).replace(",", "."))
    except InvalidOperation:
        return None


def _room_code(value):
    text = _norm(value)
    if "stock" in text:
        return "STOCK"
    match = re.search(r"(\d{1,2})", text)
    return f"ROOM{int(match.group(1)):02d}" if match else ""


def _room_label(code):
    if code == "STOCK":
        return "Salle de stock"
    match = re.match(r"ROOM(\d{2})$", code)
    return f"Salle {match.group(1)}" if match else code


def _serials(value):
    text = _text(value)
    if not text or _norm(text) in {"na", "n a", "sans", "non renseigne", "-"}:
        return []
    parts = [part.strip() for part in re.split(r"\s*(?:/|;|\n)\s*", text) if part.strip()]
    return parts


_UNIT_FACTORS = {
    "ml": ("VOLUME", Decimal("1")),
    "l": ("VOLUME", Decimal("1000")),
    "g": ("MASS", Decimal("1")),
    "kg": ("MASS", Decimal("1000")),
}


def _unit_token(text):
    value = unicodedata.normalize("NFKC", _text(text)).casefold().replace("ℓ", "l")
    matches = re.findall(r"(?<![a-z])(kg|ml|l|g)(?![a-z])", value)
    if not matches:
        return None
    dimensions = {_UNIT_FACTORS[token][0] for token in matches}
    if len(dimensions) != 1:
        return None
    return "ML" if next(iter(dimensions)) == "VOLUME" else "G"


def _parse_term(term):
    term = unicodedata.normalize("NFKC", term).casefold().replace(" ", "").replace(",", ".")
    forward = re.fullmatch(r"(\d+(?:\.\d+)?)(kg|ml|l|g)(?:[x×*](\d+(?:\.\d+)?))?", term)
    reverse = re.fullmatch(r"(\d+(?:\.\d+)?)[x×*](\d+(?:\.\d+)?)(kg|ml|l|g)", term)
    if forward:
        amount = Decimal(forward.group(1))
        token = forward.group(2)
        multiplier = Decimal(forward.group(3) or "1")
    elif reverse:
        multiplier = Decimal(reverse.group(1))
        amount = Decimal(reverse.group(2))
        token = reverse.group(3)
    else:
        return None
    dimension, factor = _UNIT_FACTORS[token]
    return dimension, amount * multiplier * factor


def parse_exact_quantity(value, fallback_unit=None):
    raw = _text(value)
    if not raw:
        return None, fallback_unit, "quantité restante non renseignée"
    normalized = unicodedata.normalize("NFKC", raw).casefold()
    if any(marker in normalized for marker in ("entam", "ouvert", "approx", "environ", "reste")):
        return None, fallback_unit, "quantité restante non exactement mesurable dans la source"
    if re.fullmatch(r"\s*0+(?:[.,]0+)?\s*", normalized):
        return Decimal("0"), fallback_unit, ""
    terms = [part.strip() for part in normalized.split("+")]
    parsed = [_parse_term(term) for term in terms]
    if any(item is None for item in parsed):
        return None, fallback_unit, "expression de quantité à vérifier"
    dimensions = {item[0] for item in parsed}
    if len(dimensions) != 1:
        return None, fallback_unit, "unités de dimensions différentes"
    amount = sum((item[1] for item in parsed), Decimal("0"))
    unit = "ML" if next(iter(dimensions)) == "VOLUME" else "G"
    return amount, unit, ""


def _equipment_identity(row):
    name = _field(row, "Equipment Name") or _field(row, "Model")
    return _norm(name), f"ROOM{_text(row.get('__room__')).zfill(2)}"


def _excel_equipment_identity(row):
    return _norm(_field(row, "Equipement", "Equipment")), _room_code(_field(row, "Emplacement"))


def _merge_continuations(rows):
    logical, continuations = [], []
    current = None
    for row in rows:
        product = _field(row, "Produit")
        number = _field(row, "N", "Num")
        quantity = _field(row, "Quantité", "Quantité recue", "Quantité reçue")
        if current is not None and not _text(number) and not _text(quantity):
            merged = False
            if product:
                product_key = next((key for key in current if _norm(key) == _norm("Produit")), None)
                if product_key:
                    current[product_key] = " ".join(
                        filter(None, [_text(current[product_key]), _text(product)])
                    )
                    merged = True
            packaging = _field(row, "Unité", "Conditionnement")
            if packaging:
                unit_key = next(
                    (key for key in current if _norm(key) in {_norm("Unité"), _norm("Conditionnement")}),
                    None,
                )
                if unit_key:
                    current[unit_key] = " ".join(
                        filter(None, [_text(current[unit_key]), _text(packaging)])
                    )
                    merged = True
            if merged:
                current["__continuation_rows__"].append(dict(row))
                continuations.append(dict(row))
                continue
        if product:
            current = dict(row)
            current["__continuation_rows__"] = []
            logical.append(current)
            continue
        if current is not None and not _text(number):
            fragments = [
                _text(value) for key, value in row.items()
                if not key.startswith("__") and _text(value) and "emplacement" not in _norm(key)
            ]
            if fragments:
                unit_key = next((key for key in current if _norm(key) in {"unite", "unité"}), None)
                if unit_key:
                    current[unit_key] = " ".join(filter(None, [_text(current[unit_key]), *fragments]))
                current["__continuation_rows__"].append(dict(row))
                continuations.append(dict(row))
                continue
        logical.append(dict(row))
    return logical, continuations


def _equipment_preview(manifest):
    detailed = manifest.get("equipment_room_inventory", [])
    declared_physical = 0
    planned_physical = 0
    detailed_counter = Counter()
    review = []
    for row in detailed:
        quantity = _integer(_field(row, "Quantity"))
        if quantity is None or quantity < 1:
            review.append({"source": row.get("__source_file__"), "row": row.get("__source_row__"),
                           "issue": "quantité d’équipement invalide"})
            continue
        declared_physical += quantity
        detailed_counter[_equipment_identity(row)] += quantity
        serials = _serials(_field(row, "Serial Number (S/N)", "Serial Number"))
        planned_physical += max(quantity, len(serials))
        if serials and len(serials) != quantity:
            review.append({"source": row.get("__source_file__"), "row": row.get("__source_row__"),
                           "issue": f"{quantity} unité(s), {len(serials)} numéro(s) de série"})
    _, excel_rows = _sheet(manifest, "Equipement")
    excel_counter = Counter()
    for row in excel_rows:
        quantity = _integer(_field(row, "Nombre", "Quantité")) or 0
        excel_counter[_excel_equipment_identity(row)] += quantity
    matched = set(excel_counter) & set(detailed_counter)
    return {
        "detailed_rows": len(detailed),
        "declared_physical_assets": declared_physical,
        "physical_assets": planned_physical,
        "excel_rows": len(excel_rows),
        "matched_groups": len(matched),
        "excel_only_groups": [
            {"name": key[0], "location": key[1], "quantity": excel_counter[key]}
            for key in sorted(set(excel_counter) - set(detailed_counter))
        ],
        "docx_only_groups": len(set(detailed_counter) - set(excel_counter)),
        "quantity_mismatches": [
            {"name": key[0], "location": key[1],
             "excel": excel_counter[key], "detailed": detailed_counter[key]}
            for key in sorted(matched) if excel_counter[key] != detailed_counter[key]
        ],
        "review": review,
    }


def preview_inventory(manifest):
    chemical_name, chemical_rows = _sheet(manifest, "Produit chimique")
    consumable_name, consumable_rows = _sheet(manifest, "Consommable")
    reagent_name, reagent_rows = _sheet(manifest, "Réact")
    logical_consumables, continuations = _merge_continuations(consumable_rows)
    logical_reagents, reagent_continuations = _merge_continuations(reagent_rows)
    chemical_exact = chemical_zero = chemical_review = 0
    chemical_review_rows = []
    for row in chemical_rows:
        total = _field(row, "Quantité")
        remaining = _field(row, "Quantité reste")
        fallback = _unit_token(total)
        amount, unit, issue = parse_exact_quantity(remaining, fallback)
        if issue:
            chemical_review += 1
            chemical_review_rows.append({"row": row.get("__row__"), "product": _field(row, "Produit"),
                                         "remaining": remaining, "issue": issue})
        elif amount == 0:
            chemical_zero += 1
        else:
            chemical_exact += 1
    return {
        "schema": manifest.get("schema"),
        "source": manifest.get("source"),
        "source_rows": {name: len(rows) for name, rows in manifest.get("sheets", {}).items()},
        "equipment": _equipment_preview(manifest),
        "chemicals": {
            "sheet": chemical_name,
            "rows": len(chemical_rows),
            "exact_positive_balances": chemical_exact,
            "zero_balances": chemical_zero,
            "review_balances": chemical_review,
            "review_rows": chemical_review_rows,
        },
        "consumables": {
            "sheet": consumable_name,
            "source_rows": len(consumable_rows),
            "logical_rows": len(logical_consumables),
            "continuation_rows_merged": len(continuations),
        },
        "reagents": {
            "sheet": reagent_name,
            "source_rows": len(reagent_rows),
            "logical_rows": len(logical_reagents),
            "continuation_rows_merged": len(reagent_continuations),
        },
    }


def _record_legacy(*, source_key, payload, resolution, entity=None, note=""):
    from erp.models import LegacyInventoryRecord

    existing = LegacyInventoryRecord.objects.filter(source_key=source_key).first()
    if existing:
        if existing.fingerprint != payload["fingerprint"]:
            raise ValidationError(
                f"La ligne source {source_key} a changé depuis son import initial ; aucune écriture automatique n’a été faite."
            )
        if existing.resolution == resolution and (
            entity is None or existing.entity_id == entity.pk
        ):
            return existing, False
        existing.resolution = resolution
        existing.entity_type = (
            f"{entity._meta.app_label}.{entity._meta.model_name}" if entity is not None else ""
        )
        existing.entity_id = entity.pk if entity is not None else None
        existing.note = note
        existing.version += 1
        existing.save(
            update_fields=["resolution", "entity_type", "entity_id", "note", "version", "updated_at"]
        )
        return existing, False
    record = LegacyInventoryRecord(
        source_key=source_key,
        source_file=payload["source_file"],
        source_section=payload["source_section"],
        source_row=payload["source_row"],
        kind=payload["kind"],
        fingerprint=payload["fingerprint"],
        raw_data=payload["raw_data"],
        resolution=resolution,
        entity_type=(
            f"{entity._meta.app_label}.{entity._meta.model_name}" if entity is not None else ""
        ),
        entity_id=entity.pk if entity is not None else None,
        note=note,
    )
    record.full_clean()
    record.save()
    return record, True


def _already_applied(source_key, fingerprint):
    from erp.models import LegacyInventoryRecord

    record = LegacyInventoryRecord.objects.filter(source_key=source_key).first()
    if record and record.fingerprint != fingerprint:
        raise ValidationError(
            f"Conflit de provenance pour {source_key} : la source a changé ; vérification humaine requise."
        )
    if record and record.resolution in {
        LegacyInventoryRecord.Resolution.IMPORTED,
        LegacyInventoryRecord.Resolution.REUSED,
        LegacyInventoryRecord.Resolution.SKIPPED,
    }:
        return record
    return None


def _ensure_reference(user, model, code, values):
    from erp.services.catalog import save_reference

    existing = model.objects.filter(code=code).first()
    if existing:
        return existing, False
    obj = save_reference(user, model, {"code": code, **values, "active": True})
    return obj, True


def _ensure_bootstrap_references(user):
    from erp.models import Category, LocationType, Unit

    units = {}
    for code, name, dimension, factor in (
        ("PIECE", "Pièce", Unit.Dimension.COUNT, Decimal("1")),
        ("PKG", "Conditionnement", Unit.Dimension.PACKAGE, Decimal("1")),
        ("ML", "mL", Unit.Dimension.VOLUME, Decimal("1")),
        ("G", "g", Unit.Dimension.MASS, Decimal("1")),
    ):
        units[code], _ = _ensure_reference(
            user, Unit, code, {"name": name, "dimension": dimension, "factor": factor}
        )
    categories = {}
    for code, name in (
        ("CHEMICALS", "Produits chimiques"),
        ("CONSUMABLES", "Consommables"),
        ("REAGENTS", "Réactifs"),
    ):
        categories[code], _ = _ensure_reference(user, Category, code, {"name": name})
    site_type, _ = _ensure_reference(
        user, LocationType, "PLGSITE",
        {"name": "Site PLAGENOR", "can_store": False, "cold_storage": False},
    )
    room_type, _ = _ensure_reference(
        user, LocationType, "PLGROOM",
        {"name": "Salle PLAGENOR", "can_store": False, "cold_storage": False},
    )
    storage_room_type, _ = _ensure_reference(
        user, LocationType, "PLGSTOREROOM",
        {"name": "Zone de stockage PLAGENOR", "can_store": True, "cold_storage": False},
    )
    if site_type.can_store:
        raise ValidationError(
            "Le type PLGSITE existe avec une autorisation de stockage incompatible ; "
            "corrigez-le avant la reprise de l’inventaire."
        )
    if room_type.can_store:
        raise ValidationError(
            "Le type PLGROOM existe comme zone de stockage alors qu’il doit représenter "
            "une salle physique générique. Vérification humaine requise avant import."
        )
    if not storage_room_type.can_store:
        raise ValidationError(
            "Le type PLGSTOREROOM existe sans autorisation de stockage ; "
            "vérification humaine requise avant import."
        )
    return units, categories, site_type, room_type, storage_room_type


def _ensure_location(user, code, name, kind, *, parent=None, notes="", require_storage=False):
    from erp.models import Location
    from erp.services.storage import save_location

    existing = Location.objects.filter(code=code).first()
    if existing:
        if not existing.active:
            raise ValidationError(f"L’emplacement {code} existe mais est désactivé.")
        if require_storage and not existing.kind.can_store:
            raise ValidationError(
                f"L’emplacement existant {code} n’autorise pas le stockage ; vérification humaine requise."
            )
        return existing, False
    obj = save_location(
        user,
        {
            "code": code,
            "name": name,
            "kind": kind,
            "parent": parent,
            "notes": notes,
            "active": True,
        },
    )
    return obj, True


def _storage_location_codes(manifest):
    """Return only locations explicitly used for stock in the source files."""
    codes = {"STOCK"}
    for needle, blank_means_stock in (
        ("Produit chimique", False),
        ("Consommable", True),
        ("Réact", True),
    ):
        _, rows = _sheet(manifest, needle)
        for row in rows:
            code = _room_code(_field(row, "Emplacement", "EMPLACEMENT"))
            if code:
                codes.add(code)
            elif blank_means_stock:
                codes.add("STOCK")
    return codes


def _ensure_locations(user, manifest, site_type, room_type, storage_room_type):
    root, _ = _ensure_location(
        user,
        "PLAGENOR",
        "PLAGENOR",
        site_type,
        notes="Racine des emplacements de la Plateforme Technologique en Génomique.",
    )
    codes = {"STOCK"}
    for row in manifest.get("equipment_room_inventory", []):
        room = _text(row.get("__room__"))
        if room:
            codes.add(f"ROOM{room.zfill(2)}")
    for sheet_rows in manifest.get("sheets", {}).values():
        for row in sheet_rows:
            code = _room_code(_field(row, "Emplacement", "EMPLACEMENT"))
            if code:
                codes.add(code)
    storage_codes = _storage_location_codes(manifest)
    locations = {}
    for code in sorted(codes):
        can_store = code in storage_codes
        locations[code], _ = _ensure_location(
            user,
            code,
            _room_label(code),
            storage_room_type if can_store else room_type,
            parent=root,
            notes=(
                "Zone explicitement utilisée pour le stockage dans l’inventaire physique PLAGENOR 2026."
                if can_store else
                "Salle physique reprise de l’inventaire PLAGENOR 2026 ; aucune autorisation de stockage déduite."
            ),
            require_storage=can_store,
        )
    return locations

def _article_code(kind, identity):
    prefix = {"CHEMICAL": "CHEM", "CONSUMABLE": "CONS", "REAGENT": "REAG"}[kind]
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12].upper()
    return f"INV26-{prefix}-{digest}"


def _article_identity(kind, name, packaging="", base_unit_code=""):
    if kind == "CHEMICAL":
        return f"{kind}|{_norm(name)}|{_norm(base_unit_code)}"
    return f"{kind}|{_norm(name)}|{_norm(packaging)}"


def _find_or_create_article(user, *, kind, name, packaging, category, base_unit):
    from erp.models import Article
    from erp.services.catalog import save_article

    identity = _article_identity(kind, name, packaging, base_unit.code)
    matches = []
    for candidate in Article.objects.filter(category=category):
        candidate_identity = _article_identity(
            kind,
            candidate.name,
            "" if kind == "CHEMICAL" else candidate.packaging,
            candidate.base_unit.code,
        )
        if candidate_identity == identity:
            matches.append(candidate)
    if len(matches) > 1:
        raise ValidationError(
            f"Plusieurs articles existants correspondent à « {name} » ; rapprochement manuel requis."
        )
    if matches:
        return matches[0], True
    code = _article_code(kind, identity)
    collision = Article.objects.filter(code=code).first()
    if collision:
        raise ValidationError(
            f"Collision de code {code} avec un article différent ; aucune création automatique."
        )
    values = {
        "code": code,
        "name": _text(name)[:255],
        "category": category,
        "base_unit": base_unit,
        "packaging": _text(packaging)[:255],
        "specifications": (
            "Article initialisé à partir de l’inventaire physique PLAGENOR 2026. "
            "Les valeurs source intégrales sont conservées dans la traçabilité de reprise."
        ),
        "active": True,
    }
    return save_article(user, values), False


def _deterministic_uuid(source_key):
    return uuid.uuid5(uuid.UUID("dd63db7f-8740-4bf3-93a6-f7435a0f6d95"), source_key)


def _stock_codes(source_key):
    digest = hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:12].upper()
    return f"INV26-L-{digest}", f"INV26-C-{digest}", f"LEGACY-2026-{digest}"


def _stock_existing(container_code):
    from erp.models import StockContainer

    return StockContainer.objects.filter(code=container_code).select_related(
        "lot__article", "location"
    ).first()


def _receive_initial_stock(
    user, *, source_key, article, location, amount, unit, raw, note=""
):
    from erp.models import StockContainer
    from erp.services.catalog import convert_quantity
    from erp.services.stock import receive_stock

    lot_code, container_code, manufacturer_lot = _stock_codes(source_key)
    existing = _stock_existing(container_code)
    expected = Decimal(convert_quantity(article, amount, unit)[0]).quantize(
        Decimal("0.000001")
    )
    if existing:
        if (
            existing.lot.article_id != article.pk
            or existing.location_id != location.pk
            or existing.quantity != expected
        ):
            raise ValidationError(
                f"Le contenant {container_code} existe avec d’autres données ; aucune fusion automatique."
            )
        return existing, True, ""
    preexisting = list(
        StockContainer.objects.filter(lot__article=article, location=location)
        .exclude(code__startswith="INV26-C-")
        .select_related("lot__article", "location")
    )
    if preexisting:
        exact = [container for container in preexisting if container.quantity == expected]
        if len(exact) == 1:
            return exact[0], True, ""
        return None, False, (
            f"Un stock préexistant existe déjà pour « {article.name} » à {location.code}, "
            "mais il ne peut pas être rapproché sans ambiguïté de la quantité source ; "
            "aucun stock initial supplémentaire n’a été créé."
        )
    receive_stock(
        user,
        key=_deterministic_uuid(source_key),
        article=article,
        location=location,
        manufacturer_lot=manufacturer_lot,
        lot_code=lot_code,
        container_code=container_code,
        amount=amount,
        unit=unit,
        received_on=BASELINE_DATE,
        condition="Reprise de l’inventaire physique PLAGENOR 2026 ; état détaillé non renseigné dans la source.",
        control_notes=(
            "Stock initial repris sans inventer de lot fabricant, date d’achat ou date de péremption. "
            + note
        )[:500],
        initial=True,
    )
    return _stock_existing(container_code), False, ""


def _equipment_code(row, instance, ordinal):
    room = _text(row.get("__room__")).zfill(2) or "XX"
    seed = (
        f"{ordinal}|{row.get('__source_file__')}|{row.get('__source_row__')}|"
        f"{_field(row, 'Equipment Name')}|{instance}"
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8].upper()
    return f"INV26-EQ-R{room}-{digest}-{instance:02d}"[:32]


def _equipment_instructions(row, quantity):
    parts = [
        "Inventaire PLAGENOR 2026",
        f"Modèle: {_field(row, 'Model') or 'non renseigné'}",
        f"Référence: {_field(row, 'Reference') or 'non renseignée'}",
        f"Quantité source: {quantity}",
        f"Source: {row.get('__source_file__')}; ligne {row.get('__source_row__')}",
    ]
    return " | ".join(parts)


_KNOWN_EQUIPMENT_FAMILIES = {
    "MISEQ": (("miseq",),),
    "ABI3500": (("abi", "3500"), ("3500", "genetic", "analyzer")),
    "MERMADE4": (("mermade", "4"),),
    "BIOANALYZER2100": (("bioanalyzer", "2100"), ("2100", "bioanalyzer")),
    "MALDI_SIRIUS_GP": (("maldi", "biotyper"), ("sirius", "gp")),
    "BETA_2_8_LSCPLUS": (("beta", "2", "8", "lsc"),),
}


def _matches_equipment_family(text, family):
    return any(all(token in text for token in tokens)
               for tokens in _KNOWN_EQUIPMENT_FAMILIES[family])


def _known_equipment_family(row):
    source = _norm(" ".join(filter(None, (
        _field(row, "Equipment Name"),
        _field(row, "Model"),
        _field(row, "Reference"),
    ))))
    for family in _KNOWN_EQUIPMENT_FAMILIES:
        if _matches_equipment_family(source, family):
            return family
    return ""


def _resource_matches_family(resource, family):
    candidate = _norm(" ".join(filter(None, (resource.name, resource.instructions))))
    return _matches_equipment_family(candidate, family)


def _find_existing_resource(code, serial, name, location, row):
    from erp.models import PlanningResource

    if serial:
        candidates = list(
            PlanningResource.objects.filter(
                kind=PlanningResource.Kind.EQUIPMENT, serial_number=serial
            ).select_related("location")
        )
        if len(candidates) > 1:
            return None, (
                f"Le numéro de série {serial} correspond déjà à plusieurs équipements ; "
                "rapprochement humain requis."
            ), ""
        if candidates:
            candidate = candidates[0]
            if candidate.location_id == location.pk:
                return candidate, "", "serial"
            return None, (
                f"Le numéro de série {serial} existe déjà sur « {candidate.name} » "
                f"({candidate.location.code if candidate.location_id else 'sans emplacement'}), "
                f"alors que la source courante indique « {name} » ({location.code})."
            ), ""

    family = _known_equipment_family(row)
    if family:
        family_candidates = [
            resource for resource in PlanningResource.objects.filter(
                kind=PlanningResource.Kind.EQUIPMENT, location=location
            )
            if _resource_matches_family(resource, family)
        ]
        if len(family_candidates) > 1:
            return None, (
                f"Plusieurs ressources existantes de la famille {family} sont présentes à "
                f"{location.code} ; rapprochement humain requis."
            ), ""
        if family_candidates:
            candidate = family_candidates[0]
            if serial and candidate.serial_number and candidate.serial_number != serial:
                return None, (
                    f"Ressource {family} potentiellement identique mais numéro de série divergent : "
                    f"PLAGENOR={candidate.serial_number}, source={serial}."
                ), ""
            if not serial:
                return None, (
                    f"Une ressource {family} existe déjà à {location.code}, mais la source ne fournit "
                    "pas de numéro de série permettant un rapprochement automatique sûr."
                ), ""
            return candidate, "", "canonical_family"

    by_code = PlanningResource.objects.filter(code=code).first()
    if by_code:
        return by_code, "", "source_code"
    # Generic name/location matching is intentionally forbidden: several
    # identical devices can legitimately coexist in one room.
    return None, "", ""

def _apply_detailed_equipment(user, manifest, locations, report):
    from erp.models import LegacyInventoryRecord, PlanningResource
    from erp.services.planning import save_resource

    for ordinal, row in enumerate(manifest.get("equipment_room_inventory", []), 1):
        quantity = _integer(_field(row, "Quantity"))
        row_source = row.get("__source_file__", SOURCE_ZIP)
        row_number = row.get("__source_row__")
        if quantity is None or quantity < 1:
            source_key = _source_key("EQROW", ordinal, row_source, row_number)
            payload = _source_record_payload(
                row_source, f"Salle {row.get('__room__')}", row_number,
                LegacyInventoryRecord.Kind.EQUIPMENT, row,
            )
            _record_legacy(
                source_key=source_key, payload=payload,
                resolution=LegacyInventoryRecord.Resolution.REVIEW,
                note="Quantité d’équipement absente ou non entière ; aucune création automatique.",
            )
            report["equipment_review"] += 1
            continue
        serials = _serials(_field(row, "Serial Number (S/N)", "Serial Number"))
        if serials and len(serials) != quantity:
            row_key = _source_key("EQROW", ordinal, row_source, row_number)
            row_payload = _source_record_payload(
                row_source, f"Salle {row.get('__room__')}", row_number,
                LegacyInventoryRecord.Kind.EQUIPMENT, row,
            )
            _record_legacy(
                source_key=row_key, payload=row_payload,
                resolution=LegacyInventoryRecord.Resolution.REVIEW,
                note=(
                    f"Incohérence conservée : quantité déclarée={quantity}, "
                    f"numéros de série explicites={len(serials)}. "
                    "Les numéros de série explicites sont repris comme actifs physiques ; "
                    "la divergence reste à contrôler."
                ),
            )
            report["equipment_review"] += 1
        room_code = f"ROOM{_text(row.get('__room__')).zfill(2)}"
        location = locations.get(room_code)
        if location is None:
            raise ValidationError(f"Emplacement {room_code} non préparé.")
        name = _field(row, "Equipment Name")
        if not name:
            model = _field(row, "Model")
            name = (
                f"Équipement non désigné dans la source — modèle {model}"
                if model else "Équipement non désigné dans la source"
            )
        physical_count = max(quantity, len(serials))
        for instance in range(1, physical_count + 1):
            serial = serials[instance - 1] if instance <= len(serials) else ""
            source_key = _source_key("EQ", ordinal, row_source, row_number, instance)
            raw = dict(row)
            raw["__physical_instance__"] = instance
            payload = _source_record_payload(
                row_source, f"Salle {row.get('__room__')}", row_number,
                LegacyInventoryRecord.Kind.EQUIPMENT, raw,
            )
            already = _already_applied(source_key, payload["fingerprint"])
            if already:
                report["equipment_unchanged"] += 1
                continue
            code = _equipment_code(row, instance, ordinal)
            existing, duplicate_issue, matched_by = _find_existing_resource(
                code, serial, name, location, row
            )
            if duplicate_issue:
                _record_legacy(
                    source_key=source_key,
                    payload=payload,
                    resolution=LegacyInventoryRecord.Resolution.REVIEW,
                    note=(
                        "Aucune ressource supplémentaire n’a été créée afin d’éviter un doublon "
                        "potentiel. " + duplicate_issue
                    ),
                )
                report["equipment_review"] += 1
                continue
            if existing:
                if matched_by == "canonical_family" and serial and not existing.serial_number:
                    source_note = _equipment_instructions(row, quantity)
                    instructions = existing.instructions or ""
                    if source_note not in instructions:
                        instructions = " | ".join(filter(None, (instructions, source_note)))
                    existing = save_resource(
                        user,
                        {"serial_number": serial[:120], "instructions": instructions},
                        pk=existing.pk,
                        expected=existing.version,
                    )
                    report["equipment_canonical_reused"] += 1
                _record_legacy(
                    source_key=source_key, payload=payload,
                    resolution=LegacyInventoryRecord.Resolution.REUSED,
                    entity=existing,
                    note=(
                        "Rattaché à une ressource équipement existante ; aucune duplication. "
                        f"Rapprochement: {matched_by or 'identité existante'}."
                    ),
                )
                report["equipment_reused"] += 1
                continue
            resource = save_resource(
                user,
                {
                    "code": code,
                    "name": name[:255],
                    "kind": PlanningResource.Kind.EQUIPMENT,
                    "location": location,
                    "serial_number": serial[:120],
                    "instructions": _equipment_instructions(row, quantity),
                    "active": True,
                },
            )
            note = "Équipement créé depuis l’inventaire détaillé par salle."
            if len(serials) != quantity:
                note += (
                    f" Divergence source conservée : quantité={quantity}, "
                    f"numéros de série={len(serials)}."
                )
            if not serial:
                note += " Numéro de série non renseigné dans la source."
            _record_legacy(
                source_key=source_key, payload=payload,
                resolution=LegacyInventoryRecord.Resolution.IMPORTED,
                entity=resource,
                note=note,
            )
            report["equipment_created"] += 1


def _apply_excel_equipment_reconciliation(manifest, report):
    from erp.models import LegacyInventoryRecord

    _, excel_rows = _sheet(manifest, "Equipement")
    detailed_counter = Counter()
    for row in manifest.get("equipment_room_inventory", []):
        quantity = _integer(_field(row, "Quantity")) or 0
        detailed_counter[_equipment_identity(row)] += quantity
    for row in excel_rows:
        source_key = _source_key("EQXLSX", row.get("__row__"))
        payload = _source_record_payload(
            manifest["source"]["xlsx"]["name"],
            "Equipement",
            row.get("__row__"),
            LegacyInventoryRecord.Kind.EQUIPMENT,
            row,
        )
        existing = _already_applied(source_key, payload["fingerprint"])
        if existing:
            continue
        identity = _excel_equipment_identity(row)
        quantity = _integer(_field(row, "Nombre", "Quantité")) or 0
        detailed_quantity = detailed_counter.get(identity, 0)
        if detailed_quantity and detailed_quantity == quantity:
            resolution = LegacyInventoryRecord.Resolution.REUSED
            note = (
                "Ligne rapprochée du registre détaillé DOCX par désignation et salle ; "
                "aucune création supplémentaire afin d’éviter un doublon."
            )
            report["equipment_excel_matched"] += 1
        else:
            resolution = LegacyInventoryRecord.Resolution.REVIEW
            note = (
                f"Rapprochement incomplet : Excel={quantity}, détail DOCX={detailed_quantity}. "
                "Conserver pour contrôle humain ; aucune création automatique."
            )
            report["equipment_excel_review"] += 1
        _record_legacy(
            source_key=source_key, payload=payload, resolution=resolution, note=note
        )


def _stock_row_payload(manifest, section, row, kind):
    from erp.models import LegacyInventoryRecord

    return _source_record_payload(
        manifest["source"]["xlsx"]["name"],
        section,
        row.get("__row__"),
        getattr(LegacyInventoryRecord.Kind, kind),
        row,
    )


def _apply_chemical_rows(user, manifest, categories, units, locations, report):
    from erp.models import LegacyInventoryRecord

    section, rows = _sheet(manifest, "Produit chimique")
    for row in rows:
        product = _field(row, "Produit")
        if not product:
            continue
        source_key = _source_key("CHEM", row.get("__row__"))
        payload = _stock_row_payload(manifest, section, row, "CHEMICAL")
        already = _already_applied(source_key, payload["fingerprint"])
        if already:
            report["stock_unchanged"] += 1
            continue
        total = _field(row, "Quantité")
        remaining = _field(row, "Quantité reste")
        _, remaining_unit, _ = parse_exact_quantity(remaining)
        _, total_unit, _ = parse_exact_quantity(total)
        fallback = remaining_unit or total_unit or _unit_token(total)
        base_unit = units.get(fallback or "")
        if base_unit is None:
            _record_legacy(
                source_key=source_key, payload=payload,
                resolution=LegacyInventoryRecord.Resolution.REVIEW,
                note=(
                    "Dimension de quantité impossible à établir sans hypothèse ; "
                    "aucun article opérationnel ni stock n’a été créé."
                ),
            )
            report["chemical_review"] += 1
            continue
        article, reused = _find_or_create_article(
            user,
            kind="CHEMICAL",
            name=product,
            packaging=total,
            category=categories["CHEMICALS"],
            base_unit=base_unit,
        )
        amount, quantity_unit_code, issue = parse_exact_quantity(remaining, fallback)
        if issue:
            _record_legacy(
                source_key=source_key, payload=payload,
                resolution=LegacyInventoryRecord.Resolution.REVIEW,
                entity=article,
                note=(
                    "Article rattaché au catalogue, mais aucun stock physique n’a été inventé : "
                    + issue + "."
                ),
            )
            report["chemical_review"] += 1
            continue
        if amount == 0:
            _record_legacy(
                source_key=source_key, payload=payload,
                resolution=(
                    LegacyInventoryRecord.Resolution.REUSED
                    if reused else LegacyInventoryRecord.Resolution.IMPORTED
                ),
                entity=article,
                note="Solde source égal à zéro ; article conservé au catalogue sans contenant de stock.",
            )
            report["zero_stock_rows"] += 1
            continue
        location_code = _room_code(_field(row, "Emplacement"))
        location = locations.get(location_code)
        if location is None:
            _record_legacy(
                source_key=source_key, payload=payload,
                resolution=LegacyInventoryRecord.Resolution.REVIEW,
                entity=article,
                note="Emplacement source non reconnu ; aucun stock physique créé.",
            )
            report["chemical_review"] += 1
            continue
        stock_unit = units[quantity_unit_code]
        container, existed, stock_conflict = _receive_initial_stock(
            user,
            source_key=source_key,
            article=article,
            location=location,
            amount=amount,
            unit=stock_unit,
            raw=row,
            note=f"Quantité source totale: {total}; quantité restante: {remaining}.",
        )
        if stock_conflict:
            _record_legacy(
                source_key=source_key, payload=payload,
                resolution=LegacyInventoryRecord.Resolution.REVIEW,
                entity=article,
                note=stock_conflict,
            )
            report["chemical_review"] += 1
            continue
        _record_legacy(
            source_key=source_key, payload=payload,
            resolution=(
                LegacyInventoryRecord.Resolution.REUSED
                if existed else LegacyInventoryRecord.Resolution.IMPORTED
            ),
            entity=container,
            note=(
                f"Stock initial exact repris : {amount} {stock_unit.code}. "
                "Lot fabricant et dates non renseignés dans la source, donc non inventés."
            ),
        )
        report["stock_created" if not existed else "stock_reused"] += 1


def _apply_packaged_rows(
    user, manifest, *, sheet_needle, kind, category_code, categories, units, locations, report
):
    from erp.models import LegacyInventoryRecord

    section, source_rows = _sheet(manifest, sheet_needle)
    rows, continuations = _merge_continuations(source_rows)
    for continuation in continuations:
        source_key = _source_key(f"{kind}-CONT", continuation.get("__row__"))
        payload = _stock_row_payload(manifest, section, continuation, kind)
        if not _already_applied(source_key, payload["fingerprint"]):
            _record_legacy(
                source_key=source_key, payload=payload,
                resolution=LegacyInventoryRecord.Resolution.SKIPPED,
                note="Ligne de continuation fusionnée avec le conditionnement de la ligne précédente.",
            )
            report["continuations_preserved"] += 1

    for row in rows:
        product = _field(row, "Produit")
        if not product:
            continue
        packaging = _field(row, "Unité", "Conditionnement")
        quantity_value = _field(row, "Quantité", "Quantité recue", "Quantité reçue")
        quantity = _decimal(quantity_value)
        source_key = _source_key(kind, row.get("__row__"))
        payload = _stock_row_payload(manifest, section, row, kind)
        already = _already_applied(source_key, payload["fingerprint"])
        if already:
            report["stock_unchanged"] += 1
            continue
        if quantity is None or quantity < 0 or quantity != quantity.quantize(Decimal("0.000001")):
            _record_legacy(
                source_key=source_key, payload=payload,
                resolution=LegacyInventoryRecord.Resolution.REVIEW,
                note="Quantité de conditionnements non exploitable sans interprétation humaine.",
            )
            report["packaged_review"] += 1
            continue
        article, reused = _find_or_create_article(
            user,
            kind=kind,
            name=product,
            packaging=packaging,
            category=categories[category_code],
            base_unit=units["PKG"],
        )
        if quantity == 0:
            _record_legacy(
                source_key=source_key, payload=payload,
                resolution=(
                    LegacyInventoryRecord.Resolution.REUSED
                    if reused else LegacyInventoryRecord.Resolution.IMPORTED
                ),
                entity=article,
                note="Quantité source égale à zéro ; article conservé au catalogue.",
            )
            report["zero_stock_rows"] += 1
            continue
        location_code = _room_code(_field(row, "Emplacement", "EMPLACEMENT")) or "STOCK"
        location = locations.get(location_code)
        if location is None:
            _record_legacy(
                source_key=source_key, payload=payload,
                resolution=LegacyInventoryRecord.Resolution.REVIEW,
                entity=article,
                note=f"Emplacement « {_field(row, 'Emplacement', 'EMPLACEMENT')} » non reconnu.",
            )
            report["packaged_review"] += 1
            continue
        container, existed, stock_conflict = _receive_initial_stock(
            user,
            source_key=source_key,
            article=article,
            location=location,
            amount=quantity,
            unit=units["PKG"],
            raw=row,
            note=f"Conditionnement source: {packaging}.",
        )
        if stock_conflict:
            _record_legacy(
                source_key=source_key, payload=payload,
                resolution=LegacyInventoryRecord.Resolution.REVIEW,
                entity=article,
                note=stock_conflict,
            )
            report["packaged_review"] += 1
            continue
        _record_legacy(
            source_key=source_key, payload=payload,
            resolution=(
                LegacyInventoryRecord.Resolution.REUSED
                if existed else LegacyInventoryRecord.Resolution.IMPORTED
            ),
            entity=container,
            note=(
                f"{quantity} conditionnement(s) repris comme stock initial ; "
                f"conditionnement source exact : {packaging or 'non renseigné'}."
            ),
        )
        report["stock_created" if not existed else "stock_reused"] += 1


@transaction.atomic
def apply_inventory(user, manifest):
    from erp.permissions import require_manager

    if manifest.get("schema") != SCHEMA_VERSION:
        raise ValidationError("Version de manifeste d’inventaire non prise en charge.")
    require_manager(user)
    units, categories, site_type, room_type, storage_room_type = _ensure_bootstrap_references(user)
    locations = _ensure_locations(user, manifest, site_type, room_type, storage_room_type)
    report = Counter(
        {
            "equipment_created": 0,
            "equipment_reused": 0,
            "equipment_canonical_reused": 0,
            "equipment_unchanged": 0,
            "equipment_review": 0,
            "equipment_excel_matched": 0,
            "equipment_excel_review": 0,
            "stock_created": 0,
            "stock_reused": 0,
            "stock_unchanged": 0,
            "chemical_review": 0,
            "packaged_review": 0,
            "zero_stock_rows": 0,
            "continuations_preserved": 0,
        }
    )
    _apply_detailed_equipment(user, manifest, locations, report)
    _apply_excel_equipment_reconciliation(manifest, report)
    _apply_chemical_rows(user, manifest, categories, units, locations, report)
    _apply_packaged_rows(
        user, manifest,
        sheet_needle="Consommable",
        kind="CONSUMABLE",
        category_code="CONSUMABLES",
        categories=categories,
        units=units,
        locations=locations,
        report=report,
    )
    _apply_packaged_rows(
        user, manifest,
        sheet_needle="Réact",
        kind="REAGENT",
        category_code="REAGENTS",
        categories=categories,
        units=units,
        locations=locations,
        report=report,
    )
    return dict(report)


@transaction.atomic
def review_legacy_record(user, pk, *, expected, review_status, review_note):
    """Record a human review without changing the immutable source payload."""
    from django.utils import timezone
    from erp.models import LegacyInventoryRecord
    from erp.permissions import require_manager
    from erp.services.common import audit, check_version, snapshot

    require_manager(user)
    record = LegacyInventoryRecord.objects.select_for_update().get(pk=pk)
    check_version(record, expected)
    if record.resolution != LegacyInventoryRecord.Resolution.REVIEW:
        raise ValidationError("Seules les lignes marquées « À vérifier » peuvent être clôturées.")
    allowed = {
        LegacyInventoryRecord.ReviewStatus.CONFIRMED,
        LegacyInventoryRecord.ReviewStatus.CORRECTED,
        LegacyInventoryRecord.ReviewStatus.NOT_APPLICABLE,
    }
    if review_status not in allowed:
        raise ValidationError("Choisissez une conclusion de revue valide.")
    note = _text(review_note)
    if len(note) < 5:
        raise ValidationError("Documentez la vérification ou la correction effectuée.")
    before = snapshot(record)
    record.review_status = review_status
    record.review_note = note
    record.reviewed_by = user
    record.reviewed_at = timezone.now()
    record.version += 1
    record.full_clean()
    record.save()
    audit(user, record, "legacy_inventory_reviewed", before, reason=note[:500])
    return record
