"""Internal billing assignment and document identities."""
from django.db import transaction
from django.core.exceptions import PermissionDenied, ValidationError
from core.models import Request, RequestHistory, Invoice

ESSBO_NAME = "École Supérieure en Sciences Biologiques d’Oran"
DRAFT_STATES = ('REQUEST_CREATED', 'QUOTE_DRAFT', 'QUOTE_REJECTED_BY_CLIENT')


def document_identity(req):
    from documents.genoclab_layout import CMS_DEFAULTS, cms_get
    ohb = req.billing_channel == 'OHB'
    values = {}
    for key in CMS_DEFAULTS:
        if key.startswith('genoclab_issuer_') or key.startswith('genoclab_footer_'):
            values[key] = cms_get(key.replace('genoclab_', 'ohb_'), CMS_DEFAULTS[key] if key.startswith('genoclab_issuer_address') else '') if ohb else cms_get(key)
    if ohb:
        values['genoclab_issuer_name'] = ESSBO_NAME
        values['genoclab_footer_legal'] = 'Arrêtée la présente facture à la somme de {amount_words} dinars ({amount}).'
    user = req.requester
    data = req.requester_data or {}
    name = (user.get_full_name() or user.username) if user else req.guest_name
    lines = [getattr(user, 'organization', '') or data.get('organization', ''),
             getattr(user, 'phone', '') or req.guest_phone,
             getattr(user, 'email', '') or req.guest_email]
    return {'billing_channel': req.billing_channel, 'values': values,
            'client_name': name, 'client_lines': [x for x in lines if x]}


@transaction.atomic
def assign_billing_channel(pk, channel, actor):
    if actor.role != 'PLATFORM_ADMIN':
        raise PermissionDenied('Affectation réservée à Admin Ops.')
    if channel not in ('GENOCLAB', 'OHB'):
        raise ValidationError('Canal de facturation invalide.')
    req = Request.objects.select_for_update().get(pk=pk)
    if req.channel != 'GENOCLAB' or req.status not in DRAFT_STATES or Invoice.objects.filter(request=req).exists():
        raise ValidationError('Affectation verrouillée après émission du devis.')
    if req.billing_channel != channel:
        previous = req.billing_channel
        req.billing_channel = channel
        req.quote_detail = {}
        req.quote_amount = 0
        req.quote_number = ''
        req.quote_date = None
        req.save(update_fields=['billing_channel', 'quote_detail', 'quote_amount', 'quote_number', 'quote_date', 'updated_at'])
        RequestHistory.objects.create(request=req, from_status=req.status, to_status=req.status,
                                      actor=actor, notes=f'Affectation interne : {previous} → {channel}')
    return req
