from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from hashlib import sha256
import json
from pathlib import Path
import re
import unicodedata
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction

from erp.models import (
    Article, Category, InventorySourceRecord, Location, LocationType,
    PlanningResource, Unit,
)
from erp.services.catalog import save_article, save_reference
from erp.services.planning import save_resource
from erp.services.stock import receive_stock
from erp.services.storage import save_location


ASSET = Path(__file__).resolve().parents[1] / "assets" / "inventory" / "plagenor_inventory_2026_source.json"

DOMAIN_BY_SHEET = {
    "equipement": InventorySourceRecord.Domain.EQUIPMENT,
    "produit chimique": InventorySourceRecord.Domain.CHEMICAL,
    "consommable": InventorySourceRecord.Domain.CONSUMABLE,
    "reactifs": InventorySourceRecord.Domain.REAGENT,
}
CATEGORY_SPECS = {
    InventorySourceRecord.Domain.CHEMICAL: ("INV-CHEMICAL", "Produits chimiques"),
    InventorySourceRecord.Domain.CONSUMABLE: ("INV-CONSUMABLE", "Consommables"),
    InventorySourceRecord.Domain.REAGENT: ("INV-REAGENT", "Réactifs"),
}
UNIT_SPECS = {
    "PKG": ("Conditionnement", Unit.Dimension.PACKAGE, Decimal("1")),
    "G": ("Gramme", Unit.Dimension.MASS, Decimal("0.001")),
    "ML": ("Millilitre", Unit.Dimension.VOLUME, Decimal("0.001")),
}
ROOM_TYPE = ("ROOM", "Salle PLAGENOR")
STOCK_TYPE = ("STOCK", "Stock général")
ROOT_TYPE = ("SITE", "Plateforme")
SOURCE_CONDITION = "Reprise d’inventaire PLAGENOR 2026 — état physique à confirmer"


def _fold(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold().replace("’", "'")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _sheet_key(value):
    return _fold(value)


def _safe(values, index):
    return values[index] if index < len(values) else None


def _hash_code(prefix, *parts, width=12):
    digest = sha256("|".join(_fold(p) for p in parts).encode("utf-8")).hexdigest().upper()
    return f"{prefix}-{digest[:width]}"[:32]


def _identity(*parts):
    return sha256("|".join(_fold(p) for p in parts).encode("utf-8")).hexdigest()


def _json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _room_code(value):
    folded = _fold(value)
    if "stock" in folded:
        return "STOCK-ROOM"
    match = re.search(r"(?:salle|room)\s*0*([0-9]{1,2})", folded)
    return f"ROOM-{int(match.group(1)):02d}" if match else ""


def _room_number(value):
    code = _room_code(value)
    return code[-2:] if code.startswith("ROOM-") else ""


def load_source(path=ASSET):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != 2:
        raise ValidationError("Version de source d’inventaire non reconnue.")
    return data


def _continuation_rows(rows, domain):
    """Attach source continuation rows without discarding their provenance."""
    result = []
    previous = None
    for source in rows:
        values = list(source.get("values") or [])
        product = str(_safe(values, 1) or "").strip()
        if not product and previous and domain == InventorySourceRecord.Domain.CONSUMABLE:
            continuation = str(_safe(values, 2) or "").strip()
            if continuation:
                previous["continuations"].append(source)
                previous["unit_text"] = (previous.get("unit_text", "") + " " + continuation).strip()
                continue
        if _safe(values, 0) in (None, "") and product and previous and domain == InventorySourceRecord.Domain.REAGENT:
            previous["continuations"].append(source)
            previous["product"] = (previous["product"] + " " + product).strip()
            continue
        item = {"source": source, "values": values, "continuations": [], "product": product}
        if domain == InventorySourceRecord.Domain.CONSUMABLE:
            item["unit_text"] = str(_safe(values, 2) or "").strip()
        result.append(item)
        previous = item
    return result


def workbook_rows(source):
    for raw_sheet, rows in source["xlsx"].items():
        key = _sheet_key(raw_sheet)
        domain = DOMAIN_BY_SHEET.get(key)
        if not domain:
            continue
        for item in _continuation_rows(rows[1:], domain):
            yield raw_sheet, domain, item


def _equipment_translation(value):
    text = _fold(value)
    replacements = {
        "centrifugeuse": "centrifuge", "refrigeree": "refrigerated",
        "refrigerateur": "refrigerator", "congelateur": "freezer",
        "incubateur": "incubator", "bain marie": "water bath",
        "hotte": "cabinet", "microscope": "microscope",
        "autoclave": "autoclave", "lyophilisateur": "freeze dryer",
        "spectrophotometre": "spectrophotometer", "sequenceur": "sequencer",
        "bioanalyseur": "bioanalyzer", "thermocycleur": "thermal cycler",
        "balance": "balance", "agitateur": "shaker", "cytometre": "cytometer",
        "lecteur": "reader", "laveur": "washer", "extracteur": "extraction",
        "synthetiseur": "synthesizer", "generateur": "generator",
        "armoire": "cabinet", "paillasse": "bench", "climatiseur": "air conditioner",
        "ordinateur": "computer", "imprimante": "printer",
    }
    for left, right in replacements.items():
        text = text.replace(left, right)
    return " ".join(text.split())


def _equipment_signature(value):
    text = _fold(value)
    signatures = set()
    rules = (
        ("qpcr", ("pcr en temps reel", "real time pcr", "real time thermal cycler", "qtower")),
        ("bioanalyzer", ("bioanalyzer",)),
        ("maldi", ("maldi",)),
        ("ngs", ("miseq", "next generation", "ngs", "haut debit")),
        ("sanger", ("sanger", "genetic analyzer")),
        ("scandrop", ("scandrop", "microvolume spectrophotometer")),
        ("hplc", ("hplc", "liquid chromatography")),
        ("cytometer", ("cytometre de flux", "flow cytometer")),
        ("nucleic-extractor", ("extraction d acides nucleiques", "nucleic acid extraction")),
        ("lyophilizer", ("lyophilisateur", "freeze dryer")),
        ("plate-reader", ("lecteur a microplaque", "microplate reader")),
        ("plate-washer", ("laveur automatique de microplaque", "microplate washer")),
        ("western-blot", ("western blot",)),
        ("oligo-synth", ("oligonucleotide synthesizer", "synthetiseur d oligonucleotide")),
        ("electroporator", ("electroporateur", "electroporator")),
        ("gel-doc", ("gel documentation", "gel imaging", "documentation system")),
        ("pcr-uv", ("pcr uv cabinet",)),
        ("gradient-pcr", ("thermocycleur a gradient", "gradient thermal cycler")),
        ("plate-spinner", ("microplaques pcr", "mini plate spinner")),
        ("sonicator", ("sonicateur", "ultrasonic processor")),
        ("ultrapure-water", ("eau ultra pure", "ultra pure water")),
        ("autoclave", ("autoclave", "steam sterilizer")),
        ("precision-balance", ("balance de precision", "analytical precision balance", "precision balance")),
        ("large-centrifuge", ("centrifugeuse grande capacite", "refrigerated laboratory centrifuge")),
        ("mini-centrifuge", ("centrifugeuse individuelle pour 8 microtubes", "mini centrifuge")),
        ("heated-centrifuge", ("centrifugeuse refrigeree chauffante", "refrigerated heated benchtop")),
        ("liquid-chrom", ("chromatographie avec pc", "automated liquid chromatography")),
        ("co2-incubator", ("incubateur co2", "co2 incubator")),
        ("inverted-fluorescence", ("microscope inverse a epifluorescence", "inverted fluorescence microscope")),
        ("trinocular-microscope", ("microscope trinoculaire", "trinocular microscopy")),
        ("micro-safety-cabinet", ("poste de securite microbiologique", "microbiological safety cabinet")),
        ("underbench-fridge", ("refrigerateur ventile sous paillasse", "under bench laboratory refrigerator")),
        ("incubator-shaker", ("shaker incubateur", "incubator shaker")),
        ("uv-vis", ("spectrophotometre uv visible", "uv vis double beam")),
        ("water-purifier", ("systeme d eau ultra pure", "ultrapure water system", "water purification system")),
        ("bioreactor", ("bioreacteur de paillasse", "bench top bioreactor")),
        ("laminar-cabinet", ("hotte a flux laminaire", "laminar air flow cabinet")),
        ("chemical-hood", ("hotte chimique", "chemical fume hood")),
        ("rotary-evaporator", ("evaporateur rotatif", "rotary evaporator")),
        ("colony-counter", ("compteur de colonies", "colony counter")),
        ("magnetic-stirrer", ("agitateur magnetique chauffant", "magnetic stirrer with heating")),
        ("shaking-water-bath", ("bain marie inox avec agitateur", "shaking water bath")),
        ("vortex", ("vortex",)),
        ("ph-meter", ("ph metre", "ph meter")),
    )
    for signature, needles in rules:
        if any(needle in text for needle in needles):
            signatures.add(signature)
    return signatures


def _equipment_score(left, right):
    a, b = _equipment_translation(left), _equipment_translation(right)
    if not a or not b:
        return 0.0
    score = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    if ta and tb:
        score = max(score, len(ta & tb) / min(len(ta), len(tb)))
    strong = {"maldi", "hplc", "miseq", "sanger", "bioanalyzer", "qpcr", "qubit", "cytometer", "lyophilisateur"}
    if ta & tb & strong:
        score = max(score, 0.92)
    shared_signature = _equipment_signature(left) & _equipment_signature(right)
    if shared_signature:
        score = max(score, 0.97)
    return score


def _positive_integer(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return int(number) if number == number.to_integral_value() and number > 0 else None


def room_enrichment(source, equipment_rows):
    by_room = defaultdict(list)
    for item in source["room_lists"]:
        by_room[_room_code(item.get("room"))].append(item)
    matches, used = {}, set()
    for row in equipment_rows:
        source_row = row["source"]["source_row"]
        room = _room_code(_safe(row["values"], 3))
        name = row["product"]
        expected_quantity = _positive_integer(_safe(row["values"], 2))
        candidates = []
        for docrow in by_room.get(room, []):
            key = (docrow["source_file"], docrow["table"], docrow["source_row"])
            if key in used:
                continue
            detailed_quantity = _positive_integer(_safe(docrow["values"], 4))
            if expected_quantity and detailed_quantity and expected_quantity != detailed_quantity:
                continue
            score = _equipment_score(name, _safe(docrow["values"], 1))
            if score >= 0.76:
                candidates.append((score, key, docrow))
        candidates.sort(key=lambda x: x[0], reverse=True)
        if candidates and (len(candidates) == 1 or candidates[0][0] - candidates[1][0] >= 0.08):
            score, key, docrow = candidates[0]
            matches[source_row] = {"score": score, "row": docrow}
            used.add(key)
    return matches, used


def parse_exact_chemical_balance(value):
    """Return exact physical balance only when the wording itself is unambiguous."""
    raw = str(value or "").strip()
    folded = _fold(raw)
    if not raw or "entame" in folded or "ouvert" in folded or "reste" in folded:
        return None
    parts = [p.strip() for p in re.split(r"\+", raw) if p.strip()]
    if not parts:
        return None
    dimension = None
    total = Decimal("0")
    for part in parts:
        match = re.fullmatch(
            r"\s*([0-9]+(?:[.,][0-9]+)?)\s*(kg|g|mg|l|ml)\s*(?:[xX×]\s*([0-9]+))?\s*",
            part, re.I,
        )
        if not match:
            return None
        number = Decimal(match.group(1).replace(",", "."))
        unit = match.group(2).lower()
        count = Decimal(match.group(3) or "1")
        if unit == "kg":
            unit, number = "g", number * 1000
        elif unit == "mg":
            unit, number = "g", number / 1000
        elif unit == "l":
            unit, number = "ml", number * 1000
        current = "G" if unit == "g" else "ML"
        if dimension and dimension != current:
            return None
        dimension = current
        total += number * count
    return total, dimension


def infer_chemical_unit(*values):
    text = _fold(" ".join(str(v or "") for v in values))
    if re.search(r"(?:^|[^a-z])(kg|mg|g)(?:$|[^a-z])", text):
        return "G"
    if re.search(r"(?:^|[^a-z])(ml|l)(?:$|[^a-z])", text):
        return "ML"
    return None


def _explicit_zero(value):
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value)) == 0
        except InvalidOperation:
            return False
    raw = str(value or "").strip().replace(",", ".")
    return bool(re.fullmatch(r"0+(?:\.0+)?", raw))


def _article_identity(domain, product, packaging, unit_code):
    if domain == InventorySourceRecord.Domain.CHEMICAL:
        return _identity(domain, product, unit_code)
    return _identity(domain, product, packaging, unit_code)


def _existing_article(product, unit, *, domain, packaging=""):
    folded = _fold(product)
    candidates = [
        item for item in Article.objects.filter(active=True).select_related("base_unit")
        if _fold(item.name) == folded
    ]
    if domain != InventorySourceRecord.Domain.CHEMICAL and packaging:
        same_variant = [
            item for item in candidates
            if not item.packaging or _fold(item.packaging) == _fold(packaging)
        ]
        if same_variant:
            candidates = same_variant
        elif candidates:
            return None, ""  # same name, clearly different package variant
    compatible = [
        item for item in candidates
        if item.base_unit_id == unit.pk or item.base_unit.dimension == unit.dimension
    ]
    if len(candidates) == 1 and len(compatible) == 1:
        return compatible[0], ""
    if candidates:
        return None, "Une ou plusieurs fiches article existantes de même désignation rendent le rapprochement ambigu."
    return None, ""


def _existing_equipment(name, location, serial="", *, allow_name_match=True, eligible_ids=None):
    qs = PlanningResource.objects.filter(
        active=True, kind=PlanningResource.Kind.EQUIPMENT
    ).select_related("location")
    if eligible_ids is not None:
        qs = qs.filter(pk__in=eligible_ids)
    if serial:
        serial_matches = list(qs.filter(serial_number__iexact=str(serial).strip()))
        if len(serial_matches) == 1:
            return serial_matches[0], ""
        if len(serial_matches) > 1:
            return None, "Plusieurs équipements existants portent le même numéro de série."
    if not allow_name_match:
        return None, ""
    matches = [
        item for item in qs.filter(location=location)
        if _fold(item.name) == _fold(name)
    ]
    if len(matches) == 1:
        return matches[0], ""
    if len(matches) > 1:
        return None, "Plusieurs équipements existants ont la même désignation dans cette salle."
    return None, ""


def _normal_stock_item(domain, item):
    values = item["values"]
    product = item["product"].strip()
    location = _safe(values, 4)
    if domain == InventorySourceRecord.Domain.CONSUMABLE:
        packaging = item.get("unit_text", "")
        quantity = _safe(values, 3)
        unit_code = "PKG"
        exact = Decimal(str(quantity)) if quantity not in (None, "") else None
        zero_confirmed = _explicit_zero(quantity)
    elif domain == InventorySourceRecord.Domain.REAGENT:
        packaging = str(_safe(values, 2) or "").strip()
        quantity = _safe(values, 3)
        unit_code = "PKG"
        exact = Decimal(str(quantity)) if quantity not in (None, "") else None
        zero_confirmed = _explicit_zero(quantity)
    else:
        packaging = str(_safe(values, 2) or "").strip()
        balance = _safe(values, 3)
        parsed = parse_exact_chemical_balance(balance)
        unit_code = parsed[1] if parsed else infer_chemical_unit(_safe(values, 2), balance)
        zero_confirmed = bool(parsed and parsed[0] == 0)
        if not parsed and _explicit_zero(balance):
            exact = Decimal("0")
            zero_confirmed = True
        else:
            exact = parsed[0] if parsed else None
    return {
        "product": product,
        "packaging": packaging,
        "location_code": _room_code(location),
        "location_raw": location,
        "unit_code": unit_code,
        "quantity": exact,
        "zero_confirmed": zero_confirmed,
        "identity_key": _article_identity(domain, product, packaging, unit_code or "UNKNOWN"),
    }


def summarize(path=ASSET):
    source = load_source(path)
    counts = defaultdict(int)
    unresolved = 0
    equipment = []
    for _, domain, item in workbook_rows(source):
        counts[domain] += 1
        if domain == InventorySourceRecord.Domain.EQUIPMENT:
            equipment.append(item)
        elif _normal_stock_item(domain, item)["quantity"] is None:
            unresolved += 1
    matches, used = room_enrichment(source, equipment)
    return {
        "raw_workbook_rows": {
            sheet: max(len(rows) - 1, 0) for sheet, rows in source["xlsx"].items()
        },
        "normalized_rows": dict(counts),
        "room_list_rows": len(source["room_lists"]),
        "equipment_enrichments": len(matches),
        "room_rows_needing_review": len(source["room_lists"]) - len(used),
        "stock_rows_without_exact_balance": unresolved,
        "sources": source["sources"],
    }


def _reference(user, model, code, values):
    existing = model.objects.filter(code=code).first()
    if existing:
        return existing
    return save_reference(user, model, {"code": code, **values})


def _reference_objects(user, source):
    root_kind = _reference(user, LocationType, ROOT_TYPE[0], {"name": ROOT_TYPE[1], "can_store": False})
    room_kind = _reference(user, LocationType, ROOM_TYPE[0], {"name": ROOM_TYPE[1], "can_store": True})
    stock_kind = _reference(user, LocationType, STOCK_TYPE[0], {"name": STOCK_TYPE[1], "can_store": True})
    root = Location.objects.filter(code="PLAGENOR").first()
    if root is None:
        root = save_location(user, {"code": "PLAGENOR", "name": "PLAGENOR", "kind": root_kind, "parent": None})
    locations = {"PLAGENOR": root}
    room_labels = {
        _room_code(item.get("room")): item.get("label", "")
        for item in source.get("sources", {}).get("room_archive", {}).get("files", [])
        if _room_code(item.get("room"))
    }
    for number in list(range(1, 18)):
        code = f"ROOM-{number:02d}"
        obj = Location.objects.filter(code=code).first()
        if obj is None:
            label = room_labels.get(code, "")
            obj = save_location(user, {
                "code": code,
                "name": f"Salle {number:02d}",
                "parent": root,
                "kind": room_kind,
                "notes": f"Libellé source : {label}" if label else "",
            })
        locations[code] = obj
    stock = Location.objects.filter(code="STOCK-ROOM").first()
    if stock is None:
        stock = save_location(user, {"code": "STOCK-ROOM", "name": "Salle de stock", "parent": root, "kind": stock_kind})
    locations["STOCK-ROOM"] = stock
    units = {}
    for code, (name, dimension, factor) in UNIT_SPECS.items():
        units[code] = _reference(user, Unit, code, {"name": name, "dimension": dimension, "factor": factor})
    categories = {}
    for domain, (code, name) in CATEGORY_SPECS.items():
        categories[domain] = _reference(user, Category, code, {"name": name})
    return locations, units, categories


def _source_record(source, *, domain, source_kind, source_file, source_sha, source_sheet, source_row,
                   raw_data, normalized_data, status, target=None, notes=""):
    defaults = {
        "identity_key": normalized_data.get("identity_key") or _identity(domain, source_file, source_sheet, source_row),
        "raw_data": _json_safe(raw_data),
        "normalized_data": _json_safe(normalized_data),
        "status": status,
        "target_model": target._meta.label_lower if target else "",
        "target_id": target.pk if target else None,
        "notes": notes,
    }
    obj, created = InventorySourceRecord.objects.get_or_create(
        source_sha256=source_sha,
        source_file=source_file,
        source_sheet=source_sheet,
        source_row=source_row,
        domain=domain,
        defaults={"source_kind": source_kind, **defaults},
    )
    if not created:
        # Never overwrite the raw evidence; only fill a previously unresolved target/status.
        changed = []
        if obj.status == InventorySourceRecord.Status.NEEDS_REVIEW and status != obj.status:
            obj.status = status
            changed.append("status")
        if not obj.target_id and target:
            obj.target_model = target._meta.label_lower
            obj.target_id = target.pk
            changed += ["target_model", "target_id"]
        if changed:
            obj.save(update_fields=changed + ["updated_at"])
    return obj, created


def _split_serials(value, expected):
    raw = str(value or "").strip()
    if not raw:
        return [], ""
    parts = [
        p.strip()
        for p in re.split(r"(?:[\r\n;]+|\s+/\s+)", raw)
        if p.strip()
    ]
    if len(parts) == expected:
        return parts, ""
    if expected == 1 and len(parts) == 1:
        return [raw], ""
    if len(parts) > 1:
        return [], (
            f"La fiche de salle contient {len(parts)} numéro(s) de série explicites "
            f"pour {expected} unité(s); distribution automatique refusée."
        )
    return [], (
        f"Le champ numéro de série ne peut pas être distribué avec certitude "
        f"sur {expected} unité(s); valeur source conservée sans interprétation."
    )


def _duplicate_room_serials(source):
    counts = defaultdict(int)
    for row in source.get("room_lists", []):
        raw = str(_safe(row.get("values") or [], 5) or "").strip()
        if not raw:
            continue
        parts = [
            p.strip()
            for p in re.split(r"(?:[\r\n;]+|\s+/\s+)", raw)
            if p.strip()
        ]
        for part in parts:
            counts[_fold(part)] += 1
    return {serial for serial, count in counts.items() if serial and count > 1}


@transaction.atomic
def apply_inventory(user, snapshot_date, path=ASSET):
    if not snapshot_date:
        raise ValidationError("Une date de constat d’inventaire est obligatoire pour appliquer la reprise.")
    if isinstance(snapshot_date, str):
        snapshot_date = date.fromisoformat(snapshot_date)
    source = load_source(path)
    locations, units, categories = _reference_objects(user, source)
    workbook = source["sources"]["workbook"]
    archive = source["sources"]["room_archive"]
    room_file_hashes = {
        item["filename"]: item["sha256"]
        for item in archive.get("files", [])
        if item.get("filename") and item.get("sha256")
    }
    preexisting_equipment_ids = {
        pk
        for pk, source_snapshot in PlanningResource.objects.filter(
            active=True, kind=PlanningResource.Kind.EQUIPMENT
        ).values_list("pk", "source_snapshot")
        if (source_snapshot or {}).get("sha256") != workbook["sha256"]
    }
    equipment_rows = [item for _, domain, item in workbook_rows(source) if domain == InventorySourceRecord.Domain.EQUIPMENT]
    matches, used_room_rows = room_enrichment(source, equipment_rows)
    duplicate_room_serials = _duplicate_room_serials(source)
    stats = defaultdict(int)
    equipment_targets = {}

    for sheet, domain, item in workbook_rows(source):
        row = item["source"]
        values = item["values"]
        raw = {"values": values, "continuations": item["continuations"]}
        if domain == InventorySourceRecord.Domain.EQUIPMENT:
            name = item["product"].strip()
            try:
                quantity = int(Decimal(str(_safe(values, 2) or 0)))
            except (InvalidOperation, ValueError):
                quantity = 0
            room_code = _room_code(_safe(values, 3))
            match = matches.get(row["source_row"])
            docrow = match["row"] if match else None
            normalized = {
                "identity_key": _identity("EQUIPMENT", sheet, row["source_row"]),
                "name": name,
                "quantity": quantity,
                "location_code": room_code,
                "enrichment_score": round(match["score"], 4) if match else None,
                "model": _safe(docrow["values"], 2) if docrow else "",
                "reference": _safe(docrow["values"], 3) if docrow else "",
                "serial_source": _safe(docrow["values"], 5) if docrow else "",
            }
            if quantity <= 0 or not room_code or room_code not in locations:
                _source_record(
                    source, domain=domain, source_kind="WORKBOOK", source_file=workbook["filename"],
                    source_sha=workbook["sha256"], source_sheet=sheet, source_row=row["source_row"],
                    raw_data=raw, normalized_data=normalized,
                    status=InventorySourceRecord.Status.NEEDS_REVIEW,
                    notes="Quantité ou emplacement non exploitable automatiquement.",
                )
                stats["needs_review"] += 1
                continue
            serials, serial_issue = _split_serials(normalized["serial_source"], quantity)
            duplicated = sorted({serial for serial in serials if _fold(serial) in duplicate_room_serials})
            if duplicated:
                serials = []
                duplicate_note = (
                    "Numéro(s) de série répété(s) dans plusieurs fiches de salle : "
                    + ", ".join(duplicated)
                    + ". Affectation automatique refusée."
                )
                serial_issue = " ".join(part for part in (serial_issue, duplicate_note) if part)
                normalized["duplicate_serials"] = duplicated
            normalized["serial_issue"] = serial_issue
            preexisting = {}
            ambiguities = []
            for index in range(1, quantity + 1):
                serial = serials[index - 1] if serials else ""
                candidate, note = _existing_equipment(
                    name, locations[room_code], serial,
                    allow_name_match=(quantity == 1),
                    eligible_ids=preexisting_equipment_ids,
                )
                if note:
                    ambiguities.append(note)
                if candidate:
                    preexisting[index] = candidate
            if len({obj.pk for obj in preexisting.values()}) != len(preexisting):
                ambiguities.append("Un même équipement existant correspondrait à plusieurs unités source.")
            if ambiguities:
                _source_record(
                    source, domain=domain, source_kind="WORKBOOK", source_file=workbook["filename"],
                    source_sha=workbook["sha256"], source_sheet=sheet, source_row=row["source_row"],
                    raw_data=raw, normalized_data=normalized,
                    status=InventorySourceRecord.Status.NEEDS_REVIEW,
                    notes=" ".join(sorted(set(ambiguities))),
                )
                stats["needs_review"] += 1
                continue
            resources = []
            for index in range(1, quantity + 1):
                code = f"PLG26-EQ-{row['source_row']:03d}-{index:02d}"
                obj = PlanningResource.objects.filter(code=code).first()
                created = obj is None
                if obj is not None:
                    recorded_sha = (obj.source_snapshot or {}).get("sha256")
                    if recorded_sha and recorded_sha != workbook["sha256"]:
                        raise ValidationError(
                            f"Collision de code équipement {code} avec une autre source d’inventaire."
                        )
                elif index in preexisting:
                    obj = preexisting[index]
                    created = False
                    updates = {}
                    serial = serials[index - 1] if serials else ""
                    if serial and not obj.serial_number:
                        updates["serial_number"] = serial
                    if normalized["model"] and not obj.model_name:
                        updates["model_name"] = str(normalized["model"])
                    if normalized["reference"] and not obj.manufacturer_reference:
                        updates["manufacturer_reference"] = str(normalized["reference"])
                    if updates:
                        obj = save_resource(user, updates, pk=obj.pk, expected=obj.version)
                    snapshot = {
                        "source": workbook["filename"], "sha256": workbook["sha256"],
                        "sheet": sheet, "row": row["source_row"], "raw": values,
                        "room_enrichment": docrow if docrow else None,
                        "reconciled_existing": True,
                    }
                    if not obj.source_snapshot:
                        PlanningResource.objects.filter(pk=obj.pk).update(source_snapshot=snapshot)
                        obj.source_snapshot = snapshot
                    stats["equipment_reused_existing"] += 1
                else:
                    snapshot = {
                        "source": workbook["filename"], "sha256": workbook["sha256"],
                        "sheet": sheet, "row": row["source_row"], "raw": values,
                        "room_enrichment": docrow if docrow else None,
                    }
                    obj = save_resource(user, {
                        "code": code,
                        "name": name,
                        "kind": PlanningResource.Kind.EQUIPMENT,
                        "location": locations[room_code],
                        "serial_number": serials[index - 1] if serials else "",
                        "model_name": str(normalized["model"] or ""),
                        "manufacturer_reference": str(normalized["reference"] or ""),
                        "inventory_status": "UNVERIFIED",
                    })
                    PlanningResource.objects.filter(pk=obj.pk).update(source_snapshot=snapshot)
                    obj.source_snapshot = snapshot
                resources.append(obj)
                stats["equipment_created" if created else "equipment_existing"] += 1
            target = resources[0] if resources else None
            if target:
                equipment_targets[row["source_row"]] = target
            source_status = (
                InventorySourceRecord.Status.NEEDS_REVIEW
                if serial_issue
                else (
                    InventorySourceRecord.Status.ENRICHED
                    if match else InventorySourceRecord.Status.IMPORTED
                )
            )
            _source_record(
                source, domain=domain, source_kind="WORKBOOK", source_file=workbook["filename"],
                source_sha=workbook["sha256"], source_sheet=sheet, source_row=row["source_row"],
                raw_data=raw, normalized_data=normalized,
                status=source_status,
                target=target,
                notes=(
                    f"{quantity} ressource(s) créée(s)/rattachée(s)."
                    + (f" {serial_issue}" if serial_issue else "")
                ),
            )
            if serial_issue:
                stats["needs_review"] += 1
            continue

        normalized = _normal_stock_item(domain, item)
        product = normalized["product"]
        if not product:
            continue
        unit_code = normalized["unit_code"]
        if not unit_code:
            _source_record(
                source, domain=domain, source_kind="WORKBOOK", source_file=workbook["filename"],
                source_sha=workbook["sha256"], source_sheet=sheet, source_row=row["source_row"],
                raw_data=raw, normalized_data=normalized,
                status=InventorySourceRecord.Status.NEEDS_REVIEW,
                notes="Unité physique non déterminable sans interprétation.",
            )
            stats["needs_review"] += 1
            continue
        article_code = _hash_code(
            {"CHEMICAL":"CHM","CONSUMABLE":"CON","REAGENT":"REA"}[domain],
            normalized["identity_key"], width=14,
        )
        article = Article.objects.filter(code=article_code).first()
        created = article is None
        if article is None:
            article, ambiguity = _existing_article(
                product, units[unit_code], domain=domain, packaging=normalized["packaging"]
            )
            if ambiguity:
                _source_record(
                    source, domain=domain, source_kind="WORKBOOK", source_file=workbook["filename"],
                    source_sha=workbook["sha256"], source_sheet=sheet, source_row=row["source_row"],
                    raw_data=raw, normalized_data=normalized,
                    status=InventorySourceRecord.Status.NEEDS_REVIEW, notes=ambiguity,
                )
                for continuation in item["continuations"]:
                    _source_record(
                        source, domain=domain, source_kind="WORKBOOK", source_file=workbook["filename"],
                        source_sha=workbook["sha256"], source_sheet=sheet, source_row=continuation["source_row"],
                        raw_data={"values": continuation["values"]},
                        normalized_data={"identity_key": normalized["identity_key"], "continuation_of": row["source_row"]},
                        status=InventorySourceRecord.Status.NEEDS_REVIEW,
                        notes=f"Rapprochement article parent ligne {row['source_row']} à vérifier.",
                    )
                stats["needs_review"] += 1
                continue
            if article is not None:
                created = False
                stats["articles_reused_existing"] += 1
            else:
                article = save_article(user, {
                    "code": article_code,
                    "name": product,
                    "category": categories[domain],
                    "base_unit": units[unit_code],
                    "purchase_unit": units["PKG"] if domain != InventorySourceRecord.Domain.CHEMICAL else None,
                    "packaging": normalized["packaging"],
                    "specifications": "Reprise inventaire PLAGENOR 2026. Désignation source conservée.",
                })
        stats["articles_created" if created else "articles_existing"] += 1
        quantity = normalized["quantity"]
        location = locations.get(normalized["location_code"])
        if location is None:
            _source_record(
                source, domain=domain, source_kind="WORKBOOK", source_file=workbook["filename"],
                source_sha=workbook["sha256"], source_sheet=sheet, source_row=row["source_row"],
                raw_data=raw, normalized_data=normalized,
                status=InventorySourceRecord.Status.NEEDS_REVIEW, target=article,
                notes="Article repris au catalogue; stock physique non créé faute d’emplacement exploitable.",
            )
            stats["needs_review"] += 1
        elif quantity is None or quantity < 0:
            _source_record(
                source, domain=domain, source_kind="WORKBOOK", source_file=workbook["filename"],
                source_sha=workbook["sha256"], source_sheet=sheet, source_row=row["source_row"],
                raw_data=raw, normalized_data=normalized,
                status=InventorySourceRecord.Status.NEEDS_REVIEW, target=article,
                notes="Article repris au catalogue; stock physique non créé faute de quantité résiduelle exacte.",
            )
            stats["needs_review"] += 1
        elif quantity == 0 and normalized.get("zero_confirmed"):
            _source_record(
                source, domain=domain, source_kind="WORKBOOK", source_file=workbook["filename"],
                source_sha=workbook["sha256"], source_sheet=sheet, source_row=row["source_row"],
                raw_data=raw, normalized_data=normalized,
                status=InventorySourceRecord.Status.IMPORTED, target=article,
                notes="Stock source explicitement nul; aucun contenant artificiel n’a été créé.",
            )
            stats["stock_rows_zero_confirmed"] += 1
        elif quantity == 0:
            _source_record(
                source, domain=domain, source_kind="WORKBOOK", source_file=workbook["filename"],
                source_sha=workbook["sha256"], source_sheet=sheet, source_row=row["source_row"],
                raw_data=raw, normalized_data=normalized,
                status=InventorySourceRecord.Status.NEEDS_REVIEW, target=article,
                notes="Quantité nulle non suffisamment explicite pour créer ou clôturer un stock automatiquement.",
            )
            stats["needs_review"] += 1
        else:
            lot_code = _hash_code("L", domain, row["source_row"], normalized["identity_key"], width=20)
            container_code = _hash_code("C", domain, row["source_row"], normalized["identity_key"], width=20)
            receive_stock(
                user,
                key=uuid.uuid5(uuid.NAMESPACE_URL, f"{workbook['sha256']}:{sheet}:{row['source_row']}"),
                article=article,
                location=location,
                manufacturer_lot=f"INVENTORY-UNKNOWN-{domain[:3]}-{row['source_row']}",
                lot_code=lot_code,
                container_code=container_code,
                amount=quantity,
                unit=units[unit_code],
                received_on=snapshot_date,
                condition=SOURCE_CONDITION,
                control_notes=(
                    f"Stock initial issu de {workbook['filename']} feuille {sheet} ligne {row['source_row']}. "
                    "La date enregistrée est la date technique du constat/reprise, pas une date d’achat."
                ),
                initial=True,
            )
            container = article.stock_lots.filter(code=lot_code).first().containers.filter(code=container_code).first()
            _source_record(
                source, domain=domain, source_kind="WORKBOOK", source_file=workbook["filename"],
                source_sha=workbook["sha256"], source_sheet=sheet, source_row=row["source_row"],
                raw_data=raw, normalized_data=normalized,
                status=InventorySourceRecord.Status.IMPORTED, target=container,
            )
            stats["stock_rows_imported"] += 1

        for continuation in item["continuations"]:
            _source_record(
                source, domain=domain, source_kind="WORKBOOK", source_file=workbook["filename"],
                source_sha=workbook["sha256"], source_sheet=sheet, source_row=continuation["source_row"],
                raw_data={"values": continuation["values"]},
                normalized_data={"identity_key": normalized["identity_key"], "continuation_of": row["source_row"]},
                status=InventorySourceRecord.Status.ENRICHED, target=article,
                notes=f"Ligne de continuation rattachée à la ligne source {row['source_row']}.",
            )

    # Keep every room-list line as evidence, including rows not confidently matched.
    matched_by_key = {}
    for source_row, match in matches.items():
        row = match["row"]
        matched_by_key[(row["source_file"], row["table"], row["source_row"])] = source_row
    for docrow in source["room_lists"]:
        key = (docrow["source_file"], docrow["table"], docrow["source_row"])
        workbook_row = matched_by_key.get(key)
        target = equipment_targets.get(workbook_row) if workbook_row else None
        if target is None and workbook_row:
            target = PlanningResource.objects.filter(code=f"PLG26-EQ-{workbook_row:03d}-01").first()
        normalized = {
            "identity_key": _identity("ROOM_LIST", *key),
            "room_code": _room_code(docrow.get("room")),
            "equipment_name": _safe(docrow["values"], 1),
            "model": _safe(docrow["values"], 2),
            "reference": _safe(docrow["values"], 3),
            "quantity": _safe(docrow["values"], 4),
            "serial_number": _safe(docrow["values"], 5),
            "workbook_row": workbook_row,
        }
        _source_record(
            source, domain=InventorySourceRecord.Domain.EQUIPMENT, source_kind="ROOM_LIST",
            source_file=docrow["source_file"],
            source_sha=room_file_hashes.get(docrow["source_file"], archive["sha256"]),
            source_sheet=f"{docrow.get('room','')}/Table {docrow['table']}", source_row=docrow["source_row"],
            raw_data={"values": docrow["values"]}, normalized_data=normalized,
            status=InventorySourceRecord.Status.ENRICHED if target else InventorySourceRecord.Status.NEEDS_REVIEW,
            target=target,
            notes=("" if target else "Fiche de salle conservée pour rapprochement manuel; aucun équipement actif créé automatiquement."),
        )
        stats["room_rows_enriched" if target else "room_rows_review"] += 1

    return dict(stats)
