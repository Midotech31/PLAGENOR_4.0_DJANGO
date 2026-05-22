"""Restore the configured database from a backup file (SQLite or PostgreSQL)."""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.db_backup import perform_restore


class Command(BaseCommand):
    help = 'Restore the configured database (SQLite or PostgreSQL) from a backup file.'

    def add_arguments(self, parser):
        parser.add_argument('--input', '-i', required=True, help='Path to the backup file to restore.')

    def handle(self, *args, **options):
        source = Path(options['input'])
        if not source.exists():
            raise CommandError(f'Backup file not found: {source}')
        try:
            perform_restore(source)
        except Exception as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f'Database restored from: {source}'))
