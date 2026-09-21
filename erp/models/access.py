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
