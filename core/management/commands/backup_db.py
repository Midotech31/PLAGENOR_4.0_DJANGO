"""Management command to backup the SQLite database."""
import shutil
from datetime import datetime
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Backup the SQLite database to data/backups/'

    def handle(self, *args, **options):
        db_path = settings.BASE_DIR / 'data' / 'plagenor.db'
        if not db_path.exists():
            self.stderr.write(self.style.ERROR(f'Database not found: {db_path}'))
            return

        backup_dir = settings.BASE_DIR / 'data' / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = backup_dir / f'plagenor_{timestamp}.db'
        shutil.copy2(str(db_path), str(backup_path))

        # Keep last 30 backups
        backups = sorted(backup_dir.glob('plagenor_*.db'), reverse=True)
        for old_backup in backups[30:]:
            old_backup.unlink()
            self.stdout.write(f'Deleted old backup: {old_backup.name}')

        self.stdout.write(self.style.SUCCESS(f'Backup created: {backup_path}'))
