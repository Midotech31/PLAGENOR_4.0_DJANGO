"""Centralised metrics & statistics service.

Single source of truth for every aggregation served on the dashboards and
exported in the official statistics document. All filters are kwargs on
``compute_metrics`` so the same engine drives every view (personal,
analyst, finance, admin) at different scopes.

Dimensions supported as filters AND as breakdown axes:
  * period       — date_from / date_to on Request.created_at
  * channel      — IBTIKAR / GENOCLAB
  * service      — Service.code
  * status       — Request.status
  * wilaya       — User.wilaya (requester / client side)
  * organization — User.organization (établissement)
  * gender       — User.gender (M / F)
  * analysis_frame — extracted from Request.service_params['analysis_frame']

Returns a flat dict keyed by metric name so templates iterate without
shape-matching. Heavy queries are short — a single annotated aggregate
per metric — and bounded by the same filter set.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Optional

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import (
    Avg, Count, DecimalField, F, IntegerField, Q, Sum, Value,
)
from django.db.models.functions import Coalesce, ExtractMonth, TruncMonth


# ---------------------------------------------------------------------------
# Filter parsing
# ---------------------------------------------------------------------------

def _apply_filters(qs, *, channel=None, service_code=None, status=None,
                   wilaya=None, organization=None, gender=None,
                   analysis_frame=None, date_from=None, date_to=None,
                   requester_id=None, client_id=None, assigned_member_id=None):
    """Apply every supported filter to a Request queryset. None == ignore."""
    if channel:
        qs = qs.filter(channel=channel)
    if service_code:
        qs = qs.filter(service__code=service_code)
    if status:
        if isinstance(status, (list, tuple, set)):
            qs = qs.filter(status__in=list(status))
        else:
            qs = qs.filter(status=status)
    if wilaya:
        qs = qs.filter(requester__wilaya=wilaya)
    if organization:
        qs = qs.filter(requester__organization__iexact=organization)
    if gender:
        qs = qs.filter(requester__gender=gender)
    if analysis_frame:
        # service_params is a JSONField — look up by exact key value.
        qs = qs.filter(service_params__analysis_frame=analysis_frame)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    if requester_id:
        qs = qs.filter(requester_id=requester_id)
    if client_id:
        qs = qs.filter(requester_id=client_id, channel='GENOCLAB')
    if assigned_member_id:
        qs = qs.filter(assigned_to_id=assigned_member_id)
    return qs


# ---------------------------------------------------------------------------
# Headline KPIs
# ---------------------------------------------------------------------------

REJECTED_STATES = ('REJECTED', 'DRAFT', 'QUOTE_REJECTED_BY_CLIENT')
COMPLETED_STATES = ('COMPLETED', 'CLOSED', 'ARCHIVED', 'SENT_TO_REQUESTER',
                    'SENT_TO_CLIENT')


def headline_kpis(**filters) -> dict:
    """Top-line totals scoped by ``filters``."""
    from core.models import Request
    qs = _apply_filters(Request.objects.all(), **filters)
    total = qs.count()
    rejected = qs.filter(status__in=REJECTED_STATES).count()
    completed = qs.filter(status__in=COMPLETED_STATES).count()
    in_progress = max(0, total - rejected - completed)

    ib = qs.filter(channel='IBTIKAR')
    gc = qs.filter(channel='GENOCLAB')

    ib_total = ib.aggregate(t=Coalesce(Sum('budget_amount'),
                                       Value(0, output_field=DecimalField())))['t']
    gc_total = gc.aggregate(t=Coalesce(Sum('quote_amount'),
                                       Value(0, output_field=DecimalField())))['t']

    return {
        'total': total,
        'completed': completed,
        'in_progress': in_progress,
        'rejected': rejected,
        'completion_rate': round(completed / total * 100, 1) if total else 0,
        'ibtikar_count': ib.count(),
        'genoclab_count': gc.count(),
        'ibtikar_virtual_revenue': float(ib_total or 0),
        'genoclab_revenue': float(gc_total or 0),
    }


# ---------------------------------------------------------------------------
# Breakdowns — every dimension you can group by
# ---------------------------------------------------------------------------

def breakdown_by_status(**filters) -> list[dict]:
    from core.models import Request
    qs = _apply_filters(Request.objects.all(), **filters)
    rows = (qs.values('status')
              .annotate(count=Count('id'))
              .order_by('-count'))
    status_labels = dict(Request.STATUS_CHOICES)
    return [
        {'key': r['status'],
         'label': status_labels.get(r['status'], r['status']),
         'count': r['count']}
        for r in rows
    ]


def breakdown_by_service(**filters) -> list[dict]:
    from core.models import Request
    qs = _apply_filters(Request.objects.all(), **filters)
    rows = (qs.values('service__code', 'service__name')
              .annotate(count=Count('id'),
                        ib_total=Coalesce(Sum('budget_amount',
                                              filter=Q(channel='IBTIKAR')),
                                          Value(0, output_field=DecimalField())),
                        gc_total=Coalesce(Sum('quote_amount',
                                              filter=Q(channel='GENOCLAB')),
                                          Value(0, output_field=DecimalField())))
              .order_by('-count'))
    return [
        {'key': r['service__code'] or '—',
         'label': r['service__name'] or '—',
         'count': r['count'],
         'ibtikar_total': float(r['ib_total'] or 0),
         'genoclab_total': float(r['gc_total'] or 0)}
        for r in rows
    ]


def breakdown_by_wilaya(**filters) -> list[dict]:
    """Group by requester's wilaya code. Empty wilayas grouped under '—'."""
    from core.models import Request
    from accounts.models import User
    qs = _apply_filters(Request.objects.all(), **filters)
    rows = (qs.values('requester__wilaya')
              .annotate(count=Count('id'))
              .order_by('-count'))
    wilaya_labels = dict(User.WILAYA_CHOICES)
    return [
        {'key': r['requester__wilaya'] or '',
         'label': wilaya_labels.get(r['requester__wilaya'], '—'),
         'count': r['count']}
        for r in rows
    ]


def breakdown_by_organization(**filters) -> list[dict]:
    from core.models import Request
    qs = _apply_filters(Request.objects.all(), **filters)
    rows = (qs.values('requester__organization')
              .annotate(count=Count('id'))
              .order_by('-count'))
    return [
        {'key': r['requester__organization'] or '—',
         'label': r['requester__organization'] or '—',
         'count': r['count']}
        for r in rows
    ]


def breakdown_by_gender(**filters) -> list[dict]:
    from core.models import Request
    from accounts.models import User
    qs = _apply_filters(Request.objects.all(), **filters)
    rows = (qs.values('requester__gender')
              .annotate(count=Count('id'))
              .order_by('-count'))
    g_labels = dict(User.GENDER_CHOICES)
    return [
        {'key': r['requester__gender'] or '',
         'label': g_labels.get(r['requester__gender'], '—'),
         'count': r['count']}
        for r in rows
    ]


def breakdown_by_analysis_frame(**filters) -> list[dict]:
    """Group by service_params['analysis_frame'] (Cadre de l'analyse)."""
    from core.models import Request
    qs = _apply_filters(Request.objects.all(), **filters)
    bucket: dict[str, int] = {}
    for af in qs.values_list('service_params', flat=True):
        if not isinstance(af, dict):
            continue
        key = (af.get('analysis_frame') or '').strip() or '—'
        bucket[key] = bucket.get(key, 0) + 1
    return sorted(
        ({'key': k, 'label': k, 'count': v} for k, v in bucket.items()),
        key=lambda r: -r['count'],
    )


def monthly_trend(months: int = 12, **filters) -> list[dict]:
    """Per-month request count for the last ``months`` months."""
    from core.models import Request
    cutoff = (datetime.utcnow().replace(day=1)
              - timedelta(days=31 * (months - 1))).date()
    qs = _apply_filters(Request.objects.filter(created_at__date__gte=cutoff),
                        **filters)
    rows = (qs.annotate(month=TruncMonth('created_at'))
              .values('month')
              .annotate(count=Count('id'))
              .order_by('month'))
    return [{'month': r['month'].strftime('%Y-%m'), 'count': r['count']}
            for r in rows]


# ---------------------------------------------------------------------------
# Role-aware top-level entrypoints
# ---------------------------------------------------------------------------

def stats_for_user(user, **filters) -> dict:
    """Return the appropriate stats bundle for the logged-in user's role.

    Scope rules:
      * REQUESTER / CLIENT — only their own requests
      * MEMBER (analyst)   — only requests assigned to them
      * FINANCE            — every request (financial side)
      * PLATFORM_ADMIN / SUPER_ADMIN — every request, full breakdown
    """
    role = getattr(user, 'role', '')
    if role == 'REQUESTER':
        filters = dict(filters, requester_id=user.id)
        return {
            'scope': 'personal',
            'kpis': headline_kpis(**filters),
            'by_service': breakdown_by_service(**filters),
            'by_status': breakdown_by_status(**filters),
            'trend': monthly_trend(**filters),
        }
    if role == 'CLIENT':
        filters = dict(filters, requester_id=user.id, channel='GENOCLAB')
        return {
            'scope': 'personal',
            'kpis': headline_kpis(**filters),
            'by_service': breakdown_by_service(**filters),
            'by_status': breakdown_by_status(**filters),
            'trend': monthly_trend(**filters),
        }
    if role == 'MEMBER':
        try:
            mp_id = user.member_profile.id
        except ObjectDoesNotExist:
            # Fail closed. Passing None would make _apply_filters omit the
            # analyst scope entirely and expose platform-wide statistics to a
            # MEMBER whose profile was missing/corrupt.
            mp_id = -1
        filters = dict(filters, assigned_member_id=mp_id)
        return {
            'scope': 'analyst',
            'kpis': headline_kpis(**filters),
            'by_service': breakdown_by_service(**filters),
            'by_status': breakdown_by_status(**filters),
            'trend': monthly_trend(**filters),
        }
    if role == 'FINANCE':
        return {
            'scope': 'finance',
            'kpis': headline_kpis(**filters),
            'by_service': breakdown_by_service(**filters),
            'by_status': breakdown_by_status(**filters),
            'trend': monthly_trend(**filters),
        }
    # PLATFORM_ADMIN / SUPER_ADMIN — full breakdown including demographics
    return {
        'scope': 'admin',
        'kpis': headline_kpis(**filters),
        'by_service': breakdown_by_service(**filters),
        'by_status': breakdown_by_status(**filters),
        'by_wilaya': breakdown_by_wilaya(**filters),
        'by_organization': breakdown_by_organization(**filters),
        'by_gender': breakdown_by_gender(**filters),
        'by_analysis_frame': breakdown_by_analysis_frame(**filters),
        'trend': monthly_trend(**filters),
    }
