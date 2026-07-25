"""JSON API endpoints for the service-edit modal UIs (Phase 3.8 restore).

Powers the modal-based pricing-tier editor on the SuperAdmin service-edit
page. Originally shipped in commit a6410d1 (April 2026) — lost when the
companion view layer was deleted. Restored here with a smaller, focused
surface: pricing-tier CRUD only (the form-field manager continues to use
the existing inline form). Every endpoint is admin-only and returns JSON.

URL shape (mounted in dashboard/urls.py under ``api/service/.../pricing/``):

  GET  api/service/<uuid:service_pk>/pricing/        list tiers
  POST api/service/<uuid:service_pk>/pricing/add/    create tier
  POST api/pricing/<int:pricing_pk>/                 update tier
  POST api/pricing/<int:pricing_pk>/delete/          delete tier
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from core.models import Service, ServicePricing
from dashboard.views.admin_ops import admin_required


def _serialize(tier: ServicePricing) -> dict:
    """Render a ServicePricing row for the modal UI.

    Includes every editable field plus the boolean flags. ``amount`` is
    sent as a float so the modal's ``<input type=number>`` round-trips
    cleanly; ``min_quantity`` / ``max_quantity`` / ``min_amount`` /
    ``max_amount`` are sent as null when unset so the JS doesn't paint a
    misleading "0".
    """
    return {
        'id': tier.pk,
        'name': tier.name,
        'pricing_type': tier.pricing_type,
        'channel': tier.channel,
        'amount': float(tier.amount or 0),
        'unit': tier.unit or '',
        'description': tier.description or '',
        'min_quantity': tier.min_quantity,
        'max_quantity': tier.max_quantity,
        'min_amount': float(tier.min_amount) if tier.min_amount is not None else None,
        'max_amount': float(tier.max_amount) if tier.max_amount is not None else None,
        'priority': tier.priority,
        'is_active': tier.is_active,
    }


def _apply_form_to_tier(tier: ServicePricing, post, user) -> tuple[ServicePricing | None, str | None]:
    """Apply POST values onto ``tier`` (a fresh-or-existing ServicePricing).

    Returns ``(tier, None)`` on success, ``(None, error_message)`` otherwise.
    Tolerant: blank numbers / garbage decimals fall through to sensible
    defaults rather than 500.
    """
    name = (post.get('name') or '').strip()
    if not name:
        return None, 'Le nom du tarif est obligatoire.'

    ptype = (post.get('pricing_type') or 'BASE').strip()
    if ptype not in {c for c, _ in ServicePricing.PRICING_TYPE_CHOICES}:
        return None, f'Type tarifaire invalide : {ptype}'

    channel = (post.get('channel') or 'BOTH').strip()
    if channel not in {c for c, _ in ServicePricing.CHANNEL_CHOICES}:
        return None, f'Canal invalide : {channel}'

    def _dec(v, default=None):
        if v is None or str(v).strip() == '':
            return default
        try:
            return Decimal(str(v))
        except (InvalidOperation, ValueError):
            return default

    def _int(v, default=None):
        if v is None or str(v).strip() == '':
            return default
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    tier.name = name
    tier.pricing_type = ptype
    tier.channel = channel
    tier.amount = _dec(post.get('amount'), Decimal('0')) or Decimal('0')
    tier.unit = (post.get('unit') or 'forfait').strip() or 'forfait'
    tier.description = (post.get('description') or '').strip()
    tier.min_quantity = _int(post.get('min_quantity'), 1) or 1
    tier.max_quantity = _int(post.get('max_quantity'), None)
    tier.min_amount = _dec(post.get('min_amount'), None)
    tier.max_amount = _dec(post.get('max_amount'), None)
    tier.priority = _int(post.get('priority'), 0) or 0
    tier.is_active = post.get('is_active') in ('on', 'true', '1', True)
    tier.updated_by = user
    return tier, None


@admin_required
@require_GET
def pricing_list(request, service_pk):
    """List all pricing tiers for a service (ordered by priority)."""
    service = get_object_or_404(Service, pk=service_pk)
    tiers = service.pricing_configs.order_by('priority', 'pk')
    return JsonResponse({
        'configs': [_serialize(t) for t in tiers],
        'service_id': str(service.pk),
        'service_code': service.code,
    })


@admin_required
@require_POST
def pricing_add(request, service_pk):
    """Create a new pricing tier for a service."""
    service = get_object_or_404(Service, pk=service_pk)
    tier, err = _apply_form_to_tier(ServicePricing(service=service), request.POST, request.user)
    if err:
        return JsonResponse({'error': err}, status=400)
    tier.save()
    return JsonResponse({'ok': True, 'config': _serialize(tier)}, status=201)


@admin_required
@require_POST
def pricing_update(request, pricing_pk):
    """Update an existing pricing tier."""
    tier = get_object_or_404(ServicePricing, pk=pricing_pk)
    tier, err = _apply_form_to_tier(tier, request.POST, request.user)
    if err:
        return JsonResponse({'error': err}, status=400)
    tier.save()
    return JsonResponse({'ok': True, 'config': _serialize(tier)})


@admin_required
@require_POST
def pricing_delete(request, pricing_pk):
    """Delete a pricing tier."""
    tier = get_object_or_404(ServicePricing, pk=pricing_pk)
    tier.delete()
    return JsonResponse({'ok': True})
