"""Engine-aware database backup and restore primitives.

Supports SQLite (file copy) and PostgreSQL (`pg_dump --format=custom` /
`pg_restore`). Other engines raise a clear error.

The same helpers are used by both the management commands
(`backup_db`/`restore_db`) and by the SuperAdmin dashboard views, so the UI
behaves identically across deployment configurations.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings


SQLITE_BACKUP_SUFFIX = '.db'
POSTGRES_BACKUP_SUFFIX = '.dump'  # pg_dump custom format


def _engine_name() -> str:
    """Return 'sqlite' or 'postgres' based on the configured database engine."""
    engine = settings.DATABASES['default']['ENGINE']
    if 'sqlite' in engine:
        return 'sqlite'
    if 'postgresql' in engine or 'postgres' in engine:
        return 'postgres'
    raise RuntimeError(f"Unsupported database engine for backup/restore: {engine}")


def backup_directory() -> Path:
    """Return (and create if missing) the local backup directory."""
    d = Path(settings.BASE_DIR) / 'data' / 'backups'
    d.mkdir(parents=True, exist_ok=True)
    return d


def perform_backup(keep: int = 30) -> Path:
    """Back up the configured database to `data/backups/` and return the path.

    Retains the most recent `keep` backups; older ones are pruned.
    """
    engine = _engine_name()
    db = settings.DATABASES['default']
    out_dir = backup_directory()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if engine == 'sqlite':
        src = Path(db['NAME'])
        if not src.exists():
            raise FileNotFoundError(f"SQLite database not found: {src}")
        out = out_dir / f'plagenor_{timestamp}{SQLITE_BACKUP_SUFFIX}'
        shutil.copy2(str(src), str(out))
    else:
        out = out_dir / f'plagenor_{timestamp}{POSTGRES_BACKUP_SUFFIX}'
        cmd = [
            'pg_dump', '--format=custom', '--no-owner', '--no-privileges',
            '--host', str(db.get('HOST') or 'localhost'),
            '--port', str(db.get('PORT') or '5432'),
            '--username', str(db.get('USER') or ''),
            '--dbname', str(db.get('NAME') or ''),
            '--file', str(out),
        ]
        env = os.environ.copy()
        if db.get('PASSWORD'):
            env['PGPASSWORD'] = db['PASSWORD']
        result = subprocess.run(cmd, capture_output=True, env=env, text=True)
        if result.returncode != 0:
            # Clean up partial file before raising
            try:
                out.unlink()
            except OSError:
                pass
            raise RuntimeError(f"pg_dump failed: {result.stderr.strip() or 'unknown error'}")

    _prune_old_backups(out_dir, keep=keep, protected=out)
    return out


def _prune_old_backups(out_dir: Path, keep: int, protected: Path | None = None) -> None:
    """Prune old backups without deleting the backup just created.

    SQLite ``copy2`` intentionally preserves the source mtime, which can be
    older than existing backups. Sorting only by mtime could therefore delete
    the fresh artifact immediately. ``protected`` is placed first whenever at
    least one backup is retained.
    """
    backups = sorted(
        list(out_dir.glob(f'plagenor_*{SQLITE_BACKUP_SUFFIX}'))
        + list(out_dir.glob(f'plagenor_*{POSTGRES_BACKUP_SUFFIX}')),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if keep > 0 and protected in backups:
        backups.remove(protected)
        backups.insert(0, protected)
    for old in backups[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def perform_restore(source_path: Path) -> None:
    """Restore the live database from `source_path`. The source is validated
    against the active engine before any mutation."""
    engine = _engine_name()
    db = settings.DATABASES['default']

    if engine == 'sqlite':
        _validate_sqlite(source_path)
        dst = Path(db['NAME'])
        if dst.exists():
            shutil.copy2(str(dst), str(dst.with_suffix('.pre_restore.db')))
        shutil.move(str(source_path), str(dst))
    else:
        _validate_pg_dump(source_path)
        cmd = [
            'pg_restore', '--clean', '--if-exists',
            '--no-owner', '--no-privileges',
            '--host', str(db.get('HOST') or 'localhost'),
            '--port', str(db.get('PORT') or '5432'),
            '--username', str(db.get('USER') or ''),
            '--dbname', str(db.get('NAME') or ''),
            str(source_path),
        ]
        env = os.environ.copy()
        if db.get('PASSWORD'):
            env['PGPASSWORD'] = db['PASSWORD']
        result = subprocess.run(cmd, capture_output=True, env=env, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"pg_restore failed: {result.stderr.strip() or 'unknown error'}")


def _validate_sqlite(path: Path) -> None:
    try:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("SELECT count(*) FROM sqlite_master")
        finally:
            conn.close()
    except sqlite3.Error as e:
        raise ValueError(f"Fichier SQLite invalide: {e}")


def _validate_pg_dump(path: Path) -> None:
    try:
        result = subprocess.run(
            ['pg_restore', '--list', str(path)],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        raise ValueError("pg_restore introuvable sur le serveur — installez postgresql-client.")
    if result.returncode != 0:
        raise ValueError(
            "Fichier de dump PostgreSQL invalide: "
            + (result.stderr.strip() or 'unknown error')
        )
