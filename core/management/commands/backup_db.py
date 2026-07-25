"""Backup the configured database (SQLite or PostgreSQL) to data/backups/."""
from django.core.management.base import BaseCommand, CommandError

from core.db_backup import perform_backup


class Command(BaseCommand):
    help = 'Backup the configured database (SQLite or PostgreSQL) to data/backups/.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep', type=int, default=30,
            help='Number of recent backups to retain (default: 30).',
        )

    def handle(self, *args, **options):
        try:
            path = perform_backup(keep=options['keep'])
        except Exception as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f'Backup created: {path}'))
