"""Sauvegarde et restauration locales vérifiées.

La sauvegarde contient la base (copie cohérente via l'API backup SQLite), les
documents chiffrés, les rapports, le référentiel actif, `master.key` et un
manifeste SHA-256. Elle doit être conservée sur un support chiffré : elle
contient la clé maîtresse.

La restauration s'effectue toujours sur une copie et ne remplace jamais
automatiquement des données existantes.
"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.core.crypto import sha256_bytes, sha256_file
from app.core.errors import AppError, NotFound, ValidationRefused
from app.models import Backup

MANIFEST_NAME = "MANIFESTE.json"
WARNING = (
    "Cette sauvegarde contient master.key. Sans cette clé, les données chiffrées sont "
    "définitivement illisibles ; avec elle, quiconque possède l'archive peut les lire. "
    "Conservez-la exclusivement sur un support chiffré (BitLocker recommandé)."
)


def create_backup(session: Session) -> Backup:
    settings = get_settings()
    settings.ensure_directories()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive_path = settings.backups_dir / f"sauvegarde-{stamp}.zip"
    if archive_path.exists():
        raise ValidationRefused("Une sauvegarde portant cet horodatage existe déjà.")

    snapshot = settings.temp_dir / f"db-{stamp}.sqlite3"
    _consistent_sqlite_copy(settings.db_path, snapshot)

    entries: list[dict] = []
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            _add(archive, snapshot, "base/commission_msi.sqlite3", entries)
            if settings.key_path.exists():
                _add(archive, settings.key_path, "cle/master.key", entries)
            for folder, prefix in (
                (settings.documents_dir, "documents"),
                (settings.reports_dir, "rapports"),
                (settings.regulations_dir, "reglementation"),
            ):
                for path in sorted(folder.glob("*")):
                    if path.is_file():
                        _add(archive, path, f"{prefix}/{path.name}", entries)
            rules_file = settings.data_dir.parent / "rules" / "default_rules.json"
            if rules_file.exists():
                _add(archive, rules_file, "referentiel/default_rules.json", entries)

            manifest = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "application": "Commission MSI",
                "version": settings.version,
                "designed_by": "Prof. Merzoug Mohamed",
                "warning": WARNING,
                "includes_master_key": settings.key_path.exists(),
                "files": entries,
            }
            payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            archive.writestr(MANIFEST_NAME, payload)
            manifest_digest = sha256_bytes(payload)
    finally:
        snapshot.unlink(missing_ok=True)

    record = Backup(
        archive_path=str(archive_path),
        manifest_sha256=manifest_digest,
        includes_master_key=settings.key_path.exists(),
        file_count=len(entries),
        size=archive_path.stat().st_size,
        verified=False,
    )
    session.add(record)
    audit.record(
        session,
        audit.AuditAction.BACKUP_CREATE,
        f"Sauvegarde créée ({len(entries)} fichiers) — contient master.key : "
        f"{'oui' if record.includes_master_key else 'non'}.",
        entity_type="backup",
        entity_id=record.id,
        fingerprint=f"sha256:{manifest_digest}",
    )
    session.commit()

    verification = verify_backup(session, record.id)
    if not verification["valid"]:
        raise AppError(
            "La sauvegarde vient d'être créée mais sa vérification a échoué. "
            "Elle ne doit pas être considérée comme fiable."
        )
    return record


def _add(archive: zipfile.ZipFile, path: Path, arcname: str, entries: list[dict]) -> None:
    archive.write(path, arcname)
    entries.append({"path": arcname, "sha256": sha256_file(path), "size": path.stat().st_size})


def _consistent_sqlite_copy(source: Path, target: Path) -> None:
    """Copie cohérente via l'API backup de SQLite (WAL inclus)."""
    if not source.exists():
        target.write_bytes(b"")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    origin = sqlite3.connect(str(source))
    destination = sqlite3.connect(str(target))
    try:
        with destination:
            origin.backup(destination)
    finally:
        destination.close()
        origin.close()


def verify_backup(session: Session, backup_id: str) -> dict:
    record = session.get(Backup, backup_id)
    if record is None:
        raise NotFound("Sauvegarde introuvable.")
    result = verify_archive(Path(record.archive_path))
    record.verified = result["valid"]
    audit.record(
        session,
        audit.AuditAction.BACKUP_VERIFY,
        f"Vérification de la sauvegarde : {'conforme' if result['valid'] else 'NON CONFORME'}.",
        entity_type="backup",
        entity_id=record.id,
    )
    session.commit()
    return result


def verify_archive(archive_path: Path) -> dict:
    """Vérifie chaque empreinte du manifeste, sans rien restaurer."""
    if not archive_path.exists():
        return {"valid": False, "message": "Archive introuvable.", "mismatched": []}
    mismatched: list[str] = []
    try:
        with zipfile.ZipFile(archive_path) as archive:
            manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            for entry in manifest["files"]:
                try:
                    data = archive.read(entry["path"])
                except KeyError:
                    mismatched.append(entry["path"])
                    continue
                if sha256_bytes(data) != entry["sha256"]:
                    mismatched.append(entry["path"])
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return {"valid": False, "message": "Archive illisible ou manifeste absent.", "mismatched": []}

    valid = not mismatched
    return {
        "valid": valid,
        "message": (
            "Toutes les empreintes du manifeste sont conformes."
            if valid
            else "Empreintes divergentes : la sauvegarde ne doit pas être restaurée en l'état."
        ),
        "mismatched": mismatched,
        "manifest": manifest,
    }


def restore_to_copy(session: Session, archive_path: Path, destination: Path) -> dict:
    """Restaure une sauvegarde dans un répertoire vide, jamais en écrasant.

    L'intégrité est vérifiée avant toute écriture. En cas d'échec, rien n'est
    écrit et l'installation d'origine reste intacte.
    """
    verification = verify_archive(archive_path)
    if not verification["valid"]:
        raise ValidationRefused(
            "Restauration refusée : " + verification["message"] + " L'installation d'origine est intacte."
        )
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValidationRefused(
            "Restauration refusée : le répertoire de destination n'est pas vide. "
            "Aucune donnée existante n'est jamais écrasée automatiquement."
        )
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for entry in verification["manifest"]["files"]:
            target = destination / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry["path"]))
        (destination / MANIFEST_NAME).write_bytes(archive.read(MANIFEST_NAME))

    audit.record(
        session,
        audit.AuditAction.BACKUP_RESTORE,
        f"Restauration vérifiée effectuée sur copie : {destination}.",
        entity_type="backup",
    )
    session.commit()
    return {
        "restored_to": str(destination),
        "file_count": len(verification["manifest"]["files"]),
        "message": (
            "Restauration effectuée sur copie. Vérifiez cette copie avant tout usage réel ; "
            "l'installation d'origine n'a pas été modifiée."
        ),
    }


def list_backups(session: Session) -> list[Backup]:
    from sqlalchemy import select

    return list(session.scalars(select(Backup).order_by(Backup.created_at.desc())).all())
