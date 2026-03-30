#!/usr/bin/env python3
"""
PLAGENOR 4.0 — Backup Utility
Creates timestamped backups of the SQLite database and media files.
"""

import os
import shutil
import datetime
import sys

# Resolve paths relative to this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
MEDIA_DIR = os.path.join(BASE_DIR, 'media')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')
DB_FILE = os.path.join(DATA_DIR, 'plagenor.db')

MAX_BACKUPS = 30


def create_backup():
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"plagenor_backup_{timestamp}"
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    os.makedirs(backup_path, exist_ok=True)

    # Backup database
    if os.path.exists(DB_FILE):
        shutil.copy2(DB_FILE, os.path.join(backup_path, 'plagenor.db'))
        print(f"[OK] Base de donnees sauvegardee")
    else:
        print(f"[WARN] Base de donnees introuvable: {DB_FILE}")

    # Backup media files
    if os.path.exists(MEDIA_DIR):
        media_backup = os.path.join(backup_path, 'media')
        shutil.copytree(MEDIA_DIR, media_backup)
        print(f"[OK] Fichiers media sauvegardes")
    else:
        print(f"[INFO] Aucun dossier media a sauvegarder")

    # Compress
    archive_path = shutil.make_archive(backup_path, 'zip', BACKUP_DIR, backup_name)
    shutil.rmtree(backup_path)
    print(f"[OK] Archive creee: {archive_path}")

    # Rotate old backups
    rotate_backups()

    return archive_path


def rotate_backups():
    """Keep only the most recent MAX_BACKUPS archives."""
    if not os.path.exists(BACKUP_DIR):
        return

    backups = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.endswith('.zip')],
        reverse=True,
    )

    for old_backup in backups[MAX_BACKUPS:]:
        old_path = os.path.join(BACKUP_DIR, old_backup)
        os.remove(old_path)
        print(f"[CLEAN] Ancien backup supprime: {old_backup}")


def list_backups():
    """List all existing backups."""
    if not os.path.exists(BACKUP_DIR):
        print("Aucun backup existant.")
        return

    backups = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.endswith('.zip')],
        reverse=True,
    )

    if not backups:
        print("Aucun backup existant.")
        return

    print(f"\n{'='*50}")
    print(f"  Backups PLAGENOR ({len(backups)} archives)")
    print(f"{'='*50}")
    for b in backups:
        size = os.path.getsize(os.path.join(BACKUP_DIR, b))
        size_mb = size / (1024 * 1024)
        print(f"  {b}  ({size_mb:.1f} MB)")


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'list':
        list_backups()
    else:
        print(f"\n{'='*50}")
        print(f"  PLAGENOR 4.0 — Sauvegarde")
        print(f"{'='*50}\n")
        create_backup()
        print(f"\n[DONE] Sauvegarde terminee.\n")
