"""Freeze commercial document identities independently of live CMS/profile edits."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy

active_snapshot = ContextVar('financial_document_snapshot', default=None)


def capture_issuer(billing_channel):
    from documents.genoclab_layout import CMS_DEFAULTS, cms_get
    cms = {key: cms_get(key) for key in CMS_DEFAULTS}
    if billing_channel == 'OHB':
        from core.models import PlatformContent
        # Separate issuer configuration: never inherit the subsidiary's bank
        # or tax identifiers from its live CMS configuration.
        cms = dict(CMS_DEFAULTS)
        for row in PlatformContent.objects.filter(key__startswith='ohb_', lang='fr'):
            cms[row.key.replace('ohb_', 'genoclab_', 1)] = row.value
        cms['genoclab_issuer_name'] = "École Supérieure en Sciences Biologiques d’Oran"
        cms['genoclab_vat_rate'] = '0'
    return cms


def capture_snapshot(req):
    from documents.genoclab_layout import CMS_DEFAULTS, cms_get
    user = req.requester
    data = req.requester_data or {}
    name = (user.get_full_name() or user.username) if user else req.guest_name
    lines = []
    for value in [getattr(user, 'organization', '') or data.get('institution', ''),
                  data.get('address', ''), getattr(user, 'phone', '') or req.guest_phone,
                  getattr(user, 'email', '') or req.guest_email]:
        if value:
            lines.append(str(value))
    for label, key in [('NIF', 'nif'), ('NIS', 'nis'), ('RC', 'rc')]:
        if data.get(key):
            lines.append(f'{label} : {data[key]}')
    cms = capture_issuer(req.billing_channel)
    from documents.generators import build_field_map, _resolve_block_language
    from documents.models import DocumentBlock
    from django.conf import settings
    language = _resolve_block_language(req)
    blocks = DocumentBlock.applicable_blocks(template_type='QUOTE', service=req.service, language=language)
    if not blocks.exists() and language != settings.LANGUAGE_CODE:
        blocks = DocumentBlock.applicable_blocks(template_type='QUOTE', service=req.service, language=settings.LANGUAGE_CODE)
    return {'version': 1, 'client_name': name, 'client_lines': lines,
            'billing_channel': req.billing_channel, 'cms': cms,
            'request_reference': req.display_id, 'quote_number': req.quote_number,
            'field_map': build_field_map(req),
            'quote_blocks': list(blocks.values('position', 'title', 'body'))}


def capture_invoice_snapshot(req):
    snapshot = deepcopy(req.quote_snapshot or capture_snapshot(req))
    snapshot['quote_number'] = req.quote_number
    snapshot['order_document'] = req.order_file.name.rsplit('/', 1)[-1] if req.order_file else ''
    return snapshot


@contextmanager
def frozen_document(snapshot):
    token = active_snapshot.set(deepcopy(snapshot) if snapshot else None)
    try:
        yield
    finally:
        active_snapshot.reset(token)


def ensure_quote_number(req):
    from django.db import transaction
    from django.utils import timezone
    from core.models import Request
    from core.sequences import next_value
    with transaction.atomic():
        current = Request.objects.select_for_update().get(pk=req.pk)
        if not current.quote_number:
            prefix = 'ESSBO-DEV' if current.billing_channel == 'OHB' else 'GENOCLAB-DEV'
            year = timezone.localdate().year
            # Preserve the legacy sequence, including numbers emitted before
            # quote references were stored on requests.
            scope = f'ESSBO-QUOTE-{year}' if current.billing_channel == 'OHB' else f'GENOCLAB-QUOTE-{year}'
            current.quote_number = f'{prefix}-{year}-{next_value(scope):04d}'
            current.save(update_fields=['quote_number'])
        req.quote_number = current.quote_number
    return req.quote_number


def preserve_legacy_snapshot(obj):
    """Archive the first available identity for pre-snapshot documents.

    This is an explicitly dated recovery snapshot, not a reconstruction of
    the unknown original issue-time identity or document number.
    """
    from django.db import transaction
    from django.utils import timezone
    from core.models import Invoice, Request
    from core.financial_visibility import quote_released
    from core.audit import log_action
    invoice = isinstance(obj, Invoice)
    field = 'document_snapshot' if invoice else 'quote_snapshot'
    if getattr(obj, field) or (not invoice and not quote_released(obj)):
        return
    with transaction.atomic():
        current = type(obj).objects.select_for_update().get(pk=obj.pk)
        snapshot = getattr(current, field)
        if not snapshot:
            if invoice and not current.request_id:
                client = current.client
                snapshot = {'version': 1, 'billing_channel': current.billing_channel,
                    'client_name': (client.get_full_name() or client.username) if client else '—',
                    'client_lines': [str(value) for value in [getattr(client, 'organization', ''), getattr(client, 'email', '')] if value],
                    'cms': capture_issuer(current.billing_channel)}
            else:
                snapshot = capture_invoice_snapshot(current.request) if invoice else capture_snapshot(current)
            snapshot['legacy_captured_at'] = timezone.now().isoformat()
            # Only the empty archive field is written. Issued amounts, dates,
            # status and bank/payment information are never retroactively fixed.
            type(obj).objects.filter(pk=obj.pk, **{field: {}}).update(**{field: snapshot})
            log_action('INVOICE_LEGACY_SNAPSHOT' if invoice else 'QUOTE_LEGACY_SNAPSHOT',
                       'INVOICE' if invoice else 'REQUEST', str(obj.pk), details={'captured_at': snapshot['legacy_captured_at']})
        setattr(obj, field, snapshot)
