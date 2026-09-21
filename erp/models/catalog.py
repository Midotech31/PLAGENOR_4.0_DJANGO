from decimal import Decimal
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from .common import CodedRecord, ImmutableRecord, Record


class Unit(CodedRecord):
    class Dimension(models.TextChoices):
        COUNT = 'COUNT', _('Pièces')
        VOLUME = 'VOLUME', _('Volume')
        MASS = 'MASS', _('Masse')
        TEST = 'TEST', _('Tests')
        REACTION = 'REACTION', _('Réactions')
        PACKAGE = 'PACKAGE', _('Conditionnement')
        OTHER = 'OTHER', _('Autre dimension')

    dimension = models.CharField(_('Dimension'), max_length=16, choices=Dimension.choices)
    factor = models.DecimalField(_('Facteur vers l’unité de référence'), max_digits=24,
                                 decimal_places=9, default=1,
                                 validators=[MinValueValidator(Decimal('0.000000001'))])

    class Meta(CodedRecord.Meta):
        constraints = [models.CheckConstraint(condition=Q(factor__gt=0, factor__lte=Decimal('999999999999999.999999999')), name='erp_unit_factor_positive')]


class Party(CodedRecord):
    is_supplier = models.BooleanField(_('Fournisseur'), default=True)
    is_manufacturer = models.BooleanField(_('Fabricant'), default=False)
    email = models.EmailField(_('Adresse électronique'), blank=True)
    phone = models.CharField(_('Téléphone'), max_length=64, blank=True)
    country = models.CharField(_('Pays'), max_length=100, blank=True)
    address = models.TextField(_('Adresse'), blank=True)
    notes = models.TextField(_('Observations'), blank=True)

    class Meta(CodedRecord.Meta):
        constraints = [models.CheckConstraint(condition=Q(is_supplier=True) | Q(is_manufacturer=True),
                                               name='erp_party_has_role')]


class Category(CodedRecord):
    parent = models.ForeignKey('self', verbose_name=_('Catégorie parente'), on_delete=models.PROTECT,
                               null=True, blank=True, related_name='children')


class Article(CodedRecord):
    class Criticality(models.TextChoices):
        CRITICAL = 'CRITICAL', _('Critique')
        HIGH = 'HIGH', _('Haute')
        MEDIUM = 'MEDIUM', _('Moyenne')
        LOW = 'LOW', _('Faible')

    category = models.ForeignKey(Category, verbose_name=_('Catégorie'), on_delete=models.PROTECT)
    manufacturer = models.ForeignKey(Party, verbose_name=_('Fabricant'), on_delete=models.PROTECT,
                                     null=True, blank=True, related_name='manufactured_articles')
    manufacturer_reference = models.CharField(_('Référence fabricant'), max_length=120, blank=True)
    catalog_reference = models.CharField(_('Référence catalogue'), max_length=120, blank=True, db_index=True)
    cas = models.CharField(_('Numéro CAS'), max_length=32, blank=True, db_index=True)
    concentration_value = models.DecimalField(_('Concentration'), max_digits=24, decimal_places=9, null=True, blank=True, validators=[MinValueValidator(0)])
    concentration_unit = models.ForeignKey(Unit, verbose_name=_('Unité de concentration'), on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    grade = models.CharField(_('Grade / pureté'), max_length=120, blank=True)
    format = models.CharField(_('Format'), max_length=120, blank=True)
    packaging = models.CharField(_('Conditionnement décrit'), max_length=255, blank=True)
    base_unit = models.ForeignKey(Unit, verbose_name=_('Unité de gestion'), on_delete=models.PROTECT)
    purchase_unit = models.ForeignKey(Unit, verbose_name=_('Unité d’achat'), on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    consumption_unit = models.ForeignKey(Unit, verbose_name=_('Unité de consommation'), on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    preferred_supplier = models.ForeignKey(Party, verbose_name=_('Fournisseur préféré'), on_delete=models.PROTECT,
                                           null=True, blank=True, related_name='preferred_articles')
    criticality = models.CharField(_('Criticité'), max_length=10, choices=Criticality.choices, default=Criticality.MEDIUM)
    minimum_stock = models.DecimalField(_('Stock minimal'), max_digits=18, decimal_places=6, default=0,
                                        validators=[MinValueValidator(0)])
    safety_stock = models.DecimalField(_('Stock de sécurité'), max_digits=18, decimal_places=6, default=0,
                                       validators=[MinValueValidator(0)])
    reorder_point = models.DecimalField(_('Seuil de réapprovisionnement'), max_digits=18, decimal_places=6,
                                        default=0, validators=[MinValueValidator(0)])
    target_stock = models.DecimalField(_('Stock cible'), max_digits=18, decimal_places=6, default=0,
                                       validators=[MinValueValidator(0)])
    order_multiple = models.DecimalField(_('Multiple de commande'), max_digits=18, decimal_places=6,
                                         default=1, validators=[MinValueValidator(Decimal('0.000001'))])
    lead_time_days = models.PositiveIntegerField(_('Délai fournisseur (jours)'), null=True, blank=True)
    shelf_life_days = models.PositiveIntegerField(_('Durée de conservation (jours)'), null=True, blank=True)
    after_open_days = models.PositiveIntegerField(_('Stabilité après ouverture (jours)'), null=True, blank=True)
    temperature_min = models.DecimalField(_('Température minimale (°C)'), max_digits=7, decimal_places=2, null=True, blank=True)
    temperature_max = models.DecimalField(_('Température maximale (°C)'), max_digits=7, decimal_places=2, null=True, blank=True)
    light_sensitive = models.BooleanField(_('Sensible à la lumière'), null=True, blank=True)
    specifications = models.TextField(_('Spécifications techniques'), blank=True)
    storage_instructions = models.TextField(_('Consignes de conservation'), blank=True)

    class Meta(CodedRecord.Meta):
        constraints = [
            models.CheckConstraint(condition=Q(concentration_value__isnull=True, concentration_unit__isnull=True) | Q(concentration_value__isnull=False, concentration_unit__isnull=False, concentration_value__gte=0, concentration_value__lte=Decimal('999999999999999.999999999')), name='erp_concentration_complete', violation_error_message=_('Renseignez ensemble la concentration et son unité.')),
            models.UniqueConstraint('manufacturer', Lower('manufacturer_reference'),
                                    condition=~Q(manufacturer_reference=''), name='erp_article_manufacturer_ref'),
            models.CheckConstraint(condition=Q(minimum_stock__gte=0, safety_stock__gte=0,
                                               reorder_point__gte=0, target_stock__gte=0, order_multiple__gt=0),
                                   name='erp_article_thresholds_positive'),
            models.CheckConstraint(condition=Q(temperature_min__isnull=True) | Q(temperature_max__isnull=True)
                                   | Q(temperature_min__lte=models.F('temperature_max')),
                                   name='erp_article_temperature_order'),
        ]
        indexes = [models.Index(fields=['category', 'active']), models.Index(fields=['criticality', 'active'])]


class ArticleConversion(Record):
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name='conversions')
    unit = models.ForeignKey(Unit, verbose_name=_('Unité alternative'), on_delete=models.PROTECT)
    factor = models.DecimalField(_('Quantité dans l’unité de gestion'), max_digits=24, decimal_places=9,
                                 validators=[MinValueValidator(Decimal('0.000000001'))])
    justification = models.CharField(_('Justification de la conversion'), max_length=500)
    active = models.BooleanField(_('Actif'), default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['article', 'unit'], name='erp_article_unit_unique'),
                       models.CheckConstraint(condition=Q(factor__gt=0, factor__lte=Decimal('999999999999999.999999999')), name='erp_conversion_positive')]


class PriceObservation(ImmutableRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name='prices')
    supplier = models.ForeignKey(Party, verbose_name=_('Fournisseur'), on_delete=models.PROTECT, null=True, blank=True)
    unit = models.ForeignKey(Unit, verbose_name=_('Unité du prix'), on_delete=models.PROTECT)
    amount = models.DecimalField(_('Prix unitaire'), max_digits=18, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(_('Devise'), max_length=3, default='DZD')
    observed_on = models.DateField(_('Date de référence'))
    source = models.CharField(_('Source du prix'), max_length=500)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    snapshot = models.JSONField(default=dict)

    class Meta:
        ordering = ['-observed_on', '-id']
        constraints = [models.CheckConstraint(condition=Q(amount__gte=0, amount__lte=Decimal('9999999999999999.99')), name='erp_price_nonnegative')]
