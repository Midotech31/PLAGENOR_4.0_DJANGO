#!/usr/bin/env python3
"""One-shot, fail-closed production bootstrap for the PLAGENOR 2026 inventory.

This script is deliberately outside the regular web request lifecycle. It:
1. requires an explicit operator acknowledgement;
2. creates and validates a PostgreSQL custom-format dump;
3. encrypts the dump with a key derived from the production TOTP key;
4. stores the encrypted backup in private persistent storage;
5. validates the canonical inventory preview;
6. applies the inventory in one outer transaction;
7. immediately reapplies it and proves database-level idempotence.

No database password or encryption key is printed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import parse_qs, unquote, urlsplit

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plagenor.settings")

import django

django.setup()

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection, transaction
from django.utils import timezone

from erp.models import (
    Article,
    EquipmentInventorySource,
    LegacyInventoryRecord,
    PlanningResource,
    StockContainer,
    StockMovement,
)
from erp.services.legacy_inventory import apply_inventory, load_manifest_gz, preview_inventory


ACK = "APPLY-PLAGENOR-2026"
SNAPSHOT = (
    Path(__file__).resolve().parents[1]
    / "erp"
    / "assets"
    / "bootstrap"
    / "plagenor_inventory_2026.json.gz"
)
EXPECTED_XLSX_SHA256 = "563f86e9bcdf25d15ff05ae5e876d933456180ec803cdb4ca97f680baf6fbcf4"
EXPECTED_ZIP_SHA256 = "62cb6731f08491cbce8afc17cef7a5aa6a82a279759be5884ed93511353cc109"


def _emit(event: str, **payload):
    print(json.dumps({"event": event, **payload}, ensure_ascii=False, sort_keys=True), flush=True)


def _require_ack():
    if os.getenv("PLAGENOR_INVENTORY_APPLY_ACK", "") != ACK:
        raise RuntimeError("Production inventory acknowledgement is missing or invalid.")


def _database_environment(database_url: str):
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise RuntimeError("DATABASE_URL is not a valid PostgreSQL connection string.")
    database = unquote(parsed.path.lstrip("/"))
    if not database:
        raise RuntimeError("DATABASE_URL does not specify a database.")
    env = os.environ.copy()
    env.update(
        {
            "PGHOST": parsed.hostname,
            "PGPORT": str(parsed.port or 5432),
            "PGUSER": unquote(parsed.username or ""),
            "PGPASSWORD": unquote(parsed.password or ""),
            "PGDATABASE": database,
            "PGCONNECT_TIMEOUT": "20",
        }
    )
    query = parse_qs(parsed.query)
    env["PGSSLMODE"] = query.get("sslmode", ["require"])[0] or "require"
    return env


def _backup_fernet():
    source = settings.TOTP_ENCRYPTION_KEY.encode("ascii")
    raw = base64.urlsafe_b64decode(source)
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"PLAGENOR-DB-BACKUP-v1",
        info=b"database-backup-fernet-key",
    ).derive(raw)
    return Fernet(base64.urlsafe_b64encode(derived))


def _database_counts():
    return {
        "articles": Article.objects.count(),
        "equipment_resources": PlanningResource.objects.filter(
            kind=PlanningResource.Kind.EQUIPMENT
        ).count(),
        "equipment_source_evidence": EquipmentInventorySource.objects.count(),
        "stock_containers": StockContainer.objects.count(),
        "initial_movements": StockMovement.objects.filter(
            kind=StockMovement.Kind.INITIAL
        ).count(),
        "inventory_source_records": LegacyInventoryRecord.objects.filter(
            source_key__startswith="INV26:"
        ).count(),
    }


def _server_version():
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('server_version_num')")
        return str(cursor.fetchone()[0])


def _backup_database():
    database_url = (
        os.getenv("BACKUP_DATABASE_URL")
        or os.getenv("DIRECT_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or ""
    )
    if not database_url:
        raise RuntimeError("No PostgreSQL connection URL is configured for backup.")

    pg_dump = shutil.which("pg_dump")
    pg_restore = shutil.which("pg_restore")
    if not pg_dump or not pg_restore:
        raise RuntimeError("pg_dump/pg_restore are required for production backup.")

    timestamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
    pg_env = _database_environment(database_url)
    with tempfile.TemporaryDirectory(prefix="plagenor-db-backup-") as tmp:
        dump_path = Path(tmp) / "plagenor.dump"
        subprocess.run(
            [
                pg_dump,
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(dump_path),
            ],
            env=pg_env,
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        subprocess.run(
            [pg_restore, "--list", str(dump_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        plain = dump_path.read_bytes()
        if not plain:
            raise RuntimeError("PostgreSQL backup is empty.")
        ciphertext = _backup_fernet().encrypt(plain)
        digest = hashlib.sha256(ciphertext).hexdigest()
        object_name = (
            f"database_backups/plagenor-{timestamp}-"
            f"{digest[:12]}.dump.fernet"
        )
        saved_name = default_storage.save(object_name, ContentFile(ciphertext))
        if not default_storage.exists(saved_name):
            raise RuntimeError("Encrypted database backup was not persisted.")

        metadata = {
            "created_at": timestamp,
            "cipher": "fernet-hkdf-sha256-v1",
            "ciphertext_sha256": digest,
            "plaintext_bytes": len(plain),
            "ciphertext_bytes": len(ciphertext),
            "postgres_server_version": _server_version(),
            "render_commit": os.getenv("RENDER_GIT_COMMIT", ""),
            "backup_object": saved_name,
        }
        metadata_name = default_storage.save(
            object_name + ".json",
            ContentFile(json.dumps(metadata, ensure_ascii=False, sort_keys=True).encode("utf-8")),
        )
        if not default_storage.exists(metadata_name):
            raise RuntimeError("Backup metadata was not persisted.")
        return metadata


def _validated_preview():
    manifest = load_manifest_gz(SNAPSHOT)
    source = manifest.get("source", {})
    if source.get("xlsx", {}).get("sha256") != EXPECTED_XLSX_SHA256:
        raise RuntimeError("Canonical XLSX fingerprint mismatch.")
    if source.get("zip", {}).get("sha256") != EXPECTED_ZIP_SHA256:
        raise RuntimeError("Canonical ZIP fingerprint mismatch.")

    preview = preview_inventory(manifest)
    expected = {
        ("source_rows", "Equipement"): 156,
        ("source_rows", "Produit chimique"): 82,
        ("source_rows", "Consommable"): 83,
        ("source_rows", "Réactifs"): 93,
        ("equipment", "detailed_rows"): 239,
        ("equipment", "physical_assets"): 462,
        ("chemicals", "exact_positive_balances"): 71,
        ("chemicals", "zero_balances"): 2,
        ("chemicals", "review_balances"): 9,
        ("consumables", "logical_rows"): 81,
        ("reagents", "logical_rows"): 92,
    }
    failures = []
    for (section, key), value in expected.items():
        actual = preview[section][key]
        if actual != value:
            failures.append(f"{section}.{key}: expected {value}, got {actual}")
    expected_stock_locations = {
        "ROOM03", "ROOM08", "ROOM10", "ROOM11",
        "ROOM14", "ROOM15", "ROOM16", "STOCK",
    }
    actual_stock_locations = set(preview["locations"]["stock_enabled"])
    if actual_stock_locations != expected_stock_locations:
        failures.append(
            "locations.stock_enabled: expected "
            + ",".join(sorted(expected_stock_locations))
            + " got "
            + ",".join(sorted(actual_stock_locations))
        )
    if failures:
        raise RuntimeError("Inventory preview validation failed: " + "; ".join(failures))
    return manifest, preview


def main():
    _require_ack()
    if not settings.USE_SUPABASE_STORAGE:
        raise RuntimeError("Persistent Supabase storage is required for the production backup.")

    before = _database_counts()
    _emit("inventory_bootstrap_start", before=before)

    backup = _backup_database()
    _emit(
        "inventory_backup_verified",
        backup_object=backup["backup_object"],
        ciphertext_sha256=backup["ciphertext_sha256"],
        postgres_server_version=backup["postgres_server_version"],
    )

    manifest, preview = _validated_preview()
    _emit(
        "inventory_preview_verified",
        equipment_rows=preview["equipment"]["detailed_rows"],
        physical_assets=preview["equipment"]["physical_assets"],
        chemical_positive=preview["chemicals"]["exact_positive_balances"],
        chemical_review=preview["chemicals"]["review_balances"],
        consumables=preview["consumables"]["logical_rows"],
        reagents=preview["reagents"]["logical_rows"],
        stock_locations=preview["locations"]["stock_enabled"],
    )

    actor_name = os.getenv("PLAGENOR_INVENTORY_ACTOR", "admin").strip() or "admin"
    actor = get_user_model().objects.get(username=actor_name)

    with transaction.atomic():
        first = apply_inventory(actor, manifest)
        after_first = _database_counts()
        second = apply_inventory(actor, manifest)
        after_second = _database_counts()

        if after_second != after_first:
            raise RuntimeError(
                "Inventory idempotence failure: database counts changed on second application."
            )
        if second.get("equipment_created", 0) or second.get("stock_created", 0):
            raise RuntimeError(
                "Inventory idempotence failure: second application created new data."
            )

    report = {
        "completed_at": timezone.now().isoformat(),
        "actor": actor_name,
        "backup": backup,
        "before": before,
        "first_apply": first,
        "after_first": after_first,
        "second_apply": second,
        "after_second": after_second,
        "idempotent": True,
    }
    report_name = default_storage.save(
        "database_backups/inventory-bootstrap-report-"
        + timezone.now().strftime("%Y%m%dT%H%M%SZ")
        + ".json",
        ContentFile(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")),
    )
    _emit(
        "inventory_bootstrap_complete",
        report_object=report_name,
        first_apply=first,
        second_apply=second,
        after=after_second,
    )


if __name__ == "__main__":
    main()
