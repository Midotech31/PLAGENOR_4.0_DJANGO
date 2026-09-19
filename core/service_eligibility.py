from uuid import UUID

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from core.models import Service


CHANNELS = frozenset(('IBTIKAR', 'GENOCLAB'))


def services_for(channel):
    if channel not in CHANNELS:
        raise ValidationError(_('Canal de prestation invalide.'), code='invalid_channel')
    return Service.objects.filter(active=True, channel_availability__in=('BOTH', channel))


def validate_service(service, channel):
    if channel not in CHANNELS:
        raise ValidationError(_('Canal de prestation invalide.'), code='invalid_channel')
    if service is None:
        raise ValidationError(_('Service introuvable.'), code='unknown_service')
    if not service.active:
        raise ValidationError(_('Ce service est désactivé.'), code='inactive_service')
    if service.channel_availability not in ('BOTH', channel):
        raise ValidationError(_("Ce service n'est pas disponible pour ce canal."), code='incompatible_service')
    return service


def resolve_service(value, channel, *, lock=False):
    try:
        key = UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError(_('Identifiant de service invalide.'), code='invalid_service_id') from exc
    queryset = Service.objects.select_for_update() if lock else Service.objects
    return validate_service(queryset.filter(pk=key).first(), channel)
