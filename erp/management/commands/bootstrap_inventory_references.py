from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from erp.models import Category, LocationType, Unit
from erp.permissions import is_manager
from erp.services.catalog import save_reference


UNITS = [
    {'code': 'PIECE', 'name': 'Pièce', 'name_en': 'Piece', 'name_ar': 'قطعة',
     'dimension': Unit.Dimension.COUNT, 'factor': Decimal('1')},
    {'code': 'G', 'name': 'Gramme', 'name_en': 'Gram', 'name_ar': 'غرام',
     'dimension': Unit.Dimension.MASS, 'factor': Decimal('0.001')},
    {'code': 'ML', 'name': 'Millilitre', 'name_en': 'Millilitre', 'name_ar': 'ملليلتر',
     'dimension': Unit.Dimension.VOLUME, 'factor': Decimal('0.001')},
    {'code': 'PACK', 'name': 'Conditionnement inventorié', 'name_en': 'Inventoried package',
     'name_ar': 'وحدة تعبئة بالجرد', 'dimension': Unit.Dimension.PACKAGE, 'factor': Decimal('1')},
]
CATEGORIES = [
    {'code': 'EQUIPMENT', 'name': 'Équipements', 'name_en': 'Equipment', 'name_ar': 'معدات'},
    {'code': 'CHEMICALS', 'name': 'Produits chimiques', 'name_en': 'Chemicals', 'name_ar': 'مواد كيميائية'},
    {'code': 'CONSUMABLES', 'name': 'Consommables', 'name_en': 'Consumables', 'name_ar': 'مستهلكات'},
    {'code': 'REAGENTS', 'name': 'Réactifs', 'name_en': 'Reagents', 'name_ar': 'كواشف'},
]
LOCATION_TYPES = [
    {'code': 'SITE', 'name': 'Site', 'name_en': 'Site', 'name_ar': 'موقع',
     'can_store': False, 'cold_storage': False},
    {'code': 'PLAGENOR_ROOM', 'name': 'Salle / zone de stockage', 'name_en': 'Room / storage area',
     'name_ar': 'قاعة / منطقة تخزين', 'can_store': True, 'cold_storage': False},
]


class Command(BaseCommand):
    help = 'Prépare les référentiels minimaux nécessaires à la reprise contrôlée de l’inventaire PLAGENOR 2026.'

    def add_arguments(self, parser):
        parser.add_argument('--actor', required=True, help='Nom utilisateur Admin Ops / gestionnaire ERP.')
        parser.add_argument('--apply', action='store_true', help='Créer uniquement les référentiels absents après contrôle.')

    def handle(self, *args, **options):
        try:
            actor = get_user_model().objects.get(username=options['actor'])
        except get_user_model().DoesNotExist as exc:
            raise CommandError('Utilisateur introuvable.') from exc
        if not is_manager(actor):
            raise CommandError('Le compte doit être un gestionnaire ERP / Admin Ops.')

        plan = [
            (Unit, UNITS, 'unités'),
            (Category, CATEGORIES, 'catégories'),
            (LocationType, LOCATION_TYPES, 'types d’emplacements'),
        ]
        missing = []
        for model, rows, label in plan:
            for values in rows:
                existing = model.objects.filter(code=values['code']).first()
                if existing is None:
                    missing.append((model, values))
                    self.stdout.write(f"[À créer] {label}: {values['code']} — {values['name']}")
                    continue
                if model is Unit and (
                    existing.dimension != values['dimension'] or Decimal(existing.factor) != values['factor']
                ):
                    raise CommandError(f"Le code unité {existing.code} existe avec une dimension/facteur incompatible.")
                if model is LocationType and (
                    existing.can_store != values['can_store'] or existing.cold_storage != values['cold_storage']
                ):
                    raise CommandError(f"Le type d’emplacement {existing.code} existe avec une configuration incompatible.")
                self.stdout.write(f"[Existant] {label}: {existing.code}")

        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                f"Aucune écriture effectuée. {len(missing)} référentiel(s) seraient créés. Relancez avec --apply."
            ))
            return

        with transaction.atomic():
            for model, values in missing:
                save_reference(actor, model, dict(values))
        self.stdout.write(self.style.SUCCESS(
            f"Référentiels PLAGENOR 2026 prêts : {len(missing)} création(s), aucun doublon créé."
        ))
