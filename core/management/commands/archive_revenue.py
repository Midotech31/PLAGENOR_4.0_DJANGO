from django.core.management.base import BaseCommand
from core.financial import archive_monthly_revenue


class Command(BaseCommand):
    help = 'Archive monthly revenue for IBTIKAR and GENOCLAB channels'

    def add_arguments(self, parser):
        parser.add_argument('--month', type=int, help='Month to archive (1-12)')
        parser.add_argument('--year', type=int, help='Year to archive')

    def handle(self, *args, **options):
        month = options.get('month')
        year = options.get('year')
        results = archive_monthly_revenue(month=month, year=year)
        for r in results:
            status = 'Created' if r['created'] else 'Updated'
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{status}] {r['channel']} {r['month']}/{r['year']}: "
                    f"{r['total_revenue']:,.2f} DA ({r['request_count']} demandes)"
                )
            )
