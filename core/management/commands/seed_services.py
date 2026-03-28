"""Seed Service objects from YAML registry files."""
from django.core.management.base import BaseCommand
from core.registry import load_service_registry
from core.models import Service


class Command(BaseCommand):
    help = 'Seed services from YAML registry into database'

    def handle(self, *args, **options):
        registry = load_service_registry()
        for code, defn in registry.items():
            pricing = defn.get('pricing', {})
            base_price = pricing.get('base_price', {})
            unit_price = pricing.get('unit_price', 0)

            # Calculate prices from various pricing structures
            if isinstance(base_price, dict) and base_price:
                ibtikar_price = base_price.get('non_pathogenic', 0) or list(base_price.values())[0]
                genoclab_price = base_price.get('pathogenic', 0) or ibtikar_price
            elif unit_price:
                ibtikar_price = unit_price
                genoclab_price = unit_price
            else:
                ibtikar_price = 0
                genoclab_price = 0

            svc, created = Service.objects.update_or_create(
                code=code,
                defaults={
                    'name': defn.get('service_name', code),
                    'description': defn.get('description', ''),
                    'channel_availability': 'BOTH',
                    'ibtikar_price': ibtikar_price,
                    'genoclab_price': genoclab_price,
                    'turnaround_days': 7,
                    'active': True,
                }
            )
            status = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(f'[{status}] {code}: {svc.name}'))
