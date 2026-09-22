from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .common import ImmutableRecord,Record


def expiry_windows():
    return [180,90,60,30,7]


class AlertPolicy(Record):
    key=models.CharField(max_length=32,default='PLAGENOR',unique=True,editable=False)
    expiry_days=models.JSONField(_('Seuils de péremption (jours)'),default=expiry_windows)
    dormant_days=models.PositiveIntegerField(_('Absence de consommation (jours)'),default=180)
    receipt_pending_days=models.PositiveIntegerField(_('Réception en attente depuis (jours)'),default=2)
    occupancy_percent=models.DecimalField(_('Occupation à signaler (%)'),max_digits=5,decimal_places=2,default=Decimal('90'))
    overstock_multiplier=models.DecimalField(_('Surstock : multiple du stock cible'),max_digits=6,decimal_places=2,default=Decimal('2'))
    digest_enabled=models.BooleanField(_('Activer la synthèse quotidienne dans les notifications'),default=True)

    class Meta:
        constraints=[models.CheckConstraint(condition=Q(occupancy_percent__gt=0,occupancy_percent__lte=100),name='erp_alert_occupancy_percentage'),
            models.CheckConstraint(condition=Q(overstock_multiplier__gte=1,overstock_multiplier__lte=100),name='erp_alert_overstock_multiple')]


class AlertAcknowledgement(ImmutableRecord):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    signature=models.CharField(max_length=64)
    data=models.JSONField()
    reason=models.CharField(_('Action engagée / observation'),max_length=500)
    work=models.ForeignKey('erp.WorkItem',on_delete=models.PROTECT,null=True,blank=True,related_name='alert_acknowledgements')

    class Meta:
        constraints=[models.UniqueConstraint(fields=['user','signature'],name='erp_alert_ack_unique')]
        ordering=['-created_at']


class AlertDigest(ImmutableRecord):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    day=models.DateField()
    notification=models.OneToOneField('notifications.Notification',on_delete=models.PROTECT)
    counts=models.JSONField()

    class Meta:
        constraints=[models.UniqueConstraint(fields=['user','day'],name='erp_daily_alert_digest_unique')]
