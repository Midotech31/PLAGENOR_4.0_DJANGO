from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from .common import Record


class Capability(models.TextChoices):
    VIEW_CATALOG = 'view_catalog', _('Consulter le catalogue')
    EDIT_CATALOG = 'edit_catalog', _('Gérer le catalogue')
    VIEW_STORAGE = 'view_storage', _('Consulter les emplacements')
    EDIT_STORAGE = 'edit_storage', _('Gérer les emplacements')
    VIEW_COST = 'view_cost', _('Consulter les coûts')
    EDIT_COST = 'edit_cost', _('Enregistrer les prix')
    VIEW_STOCK = 'view_stock', _('Consulter le stock')
    RECEIVE_STOCK = 'receive_stock', _('Réceptionner le stock')
    CONSUME_STOCK = 'consume_stock', _('Enregistrer les consommations')
    TRANSFER_STOCK = 'transfer_stock', _('Transférer le stock')
    RESERVE_STOCK = 'reserve_stock', _('Réserver le stock')
    CONTROL_STOCK = 'control_stock', _('Contrôler les lots et les sorties')
    INVENTORY = 'inventory', _('Réaliser un inventaire')
    VIEW_BIOBANK = 'view_biobank', _('Consulter l’échantillothèque')
    MANAGE_BIOBANK = 'manage_biobank', _('Gérer l’échantillothèque')
    VIEW_PLANNING = 'view_planning', _('Consulter les besoins prévisionnels')
    EDIT_PLANNING = 'edit_planning', _('Préparer les besoins prévisionnels')
    REVIEW_CDC_TECHNICAL = 'review_cdc_technical', _('Effectuer la revue technique des CDC')
    REVIEW_CDC_ADMIN = 'review_cdc_admin', _('Effectuer la revue administrative et juridique des CDC')
    REVIEW_CDC_FINANCIAL = 'review_cdc_financial', _('Effectuer la revue financière des CDC')
    APPROVE_CDC = 'approve_cdc', _('Approuver définitivement les CDC')


class AccessGrant(Record):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_('Membre de l’équipe'),
                             on_delete=models.PROTECT, related_name='erp_grants')
    capability = models.CharField(_('Permission'), max_length=32, choices=Capability.choices)
    location = models.ForeignKey('erp.Location', verbose_name=_('Périmètre de stockage'),
                                 on_delete=models.PROTECT, null=True, blank=True)
    category = models.ForeignKey('erp.Category', verbose_name=_('Catégorie autorisée'),
                                 on_delete=models.PROTECT, null=True, blank=True)
    active = models.BooleanField(_('Actif'), default=True)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')

    class Meta:
        indexes = [models.Index(fields=['user', 'capability', 'active'])]
