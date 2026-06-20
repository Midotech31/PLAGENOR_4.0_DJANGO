"""Configurable activity report (bilan) engine.

Builds a structured, multi-section activity report from the Request data,
driven entirely by the admin's configuration (selected dimensions, period,
filters). Sits on top of :mod:`core.stats` (reuses ``_apply_filters`` and
``headline_kpis``) and feeds :mod:`documents.stats_excel`.

Every section is returned in a uniform shape so the Excel/Word generators
render them generically::

    {
        'key': 'by_service',
        'title': 'Par service',
        'columns': ['Libellé', 'Nombre', 'Part (%)',
                    'Montant IBTIKAR (DA)', 'Montant GENOCLAB (DA)',
                    'Montant total (DA)'],
        'rows': [['EGTP-IMT — …', 12, 34.3, 60000.0, 0.0, 60000.0], …],
        'total_row': ['Total', 35, 100.0, …, …, …],
    }

International reporting practice baked in: every breakdown carries counts,
the share of the whole (%), the financial amounts per channel and a grand
total, plus a totals row — so each table is self-contained and auditable.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import (
    Coalesce, TruncMonth, TruncQuarter, TruncYear,
)

from core.stats import _apply_filters, headline_kpis


_DEC = DecimalField(max_digits=16, decimal_places=2)


def _zero():
    return Value(Decimal('0'), output_field=_DEC)


def _amount_annots() -> dict:
    """Count + per-channel monetary totals for an annotated breakdown."""
    return dict(
        count=Count('id'),
        ib=Coalesce(Sum('budget_amount', filter=Q(channel='IBTIKAR')), _zero()),
        gc=Coalesce(Sum('quote_amount', filter=Q(channel='GENOCLAB')), _zero()),
    )


# ---------------------------------------------------------------------------
# Row builders — each returns a list of {label, count, ib, gc}
# ---------------------------------------------------------------------------

def _rows_db(qs, field, label_map=None, empty='—'):
    """Group on a single DB field with amounts (SQL-side aggregation)."""
    out = []
    for r in qs.values(field).annotate(**_amount_annots()).order_by('-count'):
        key = r[field]
        if label_map is not None:
            label = label_map.get(key, empty)
        else:
            label = key or empty
        out.append({'label': label, 'count': r['count'],
                    'ib': float(r['ib'] or 0), 'gc': float(r['gc'] or 0)})
    return out


def _rows_service(qs, _gran=None):
    out = []
    rows = (qs.values('service__code', 'service__name')
              .annotate(**_amount_annots()).order_by('-count'))
    for r in rows:
        code = r['service__code'] or '—'
        name = r['service__name'] or ''
        label = f"{code} — {name}".strip(' —') or '—'
        out.append({'label': label, 'count': r['count'],
                    'ib': float(r['ib'] or 0), 'gc': float(r['gc'] or 0)})
    return out


def _rows_category(qs, _gran=None):
    """Nature / catégorie (≈ plateforme-équipement) via the YAML registry."""
    from core.registry import get_service_def
    bucket: dict[str, dict] = {}
    for r in qs.values('service__code').annotate(**_amount_annots()):
        code = r['service__code']
        cat = '—'
        if code:
            sd = get_service_def(code) or {}
            cat = (sd.get('category') or '—')
        b = bucket.setdefault(cat, {'count': 0, 'ib': 0.0, 'gc': 0.0})
        b['count'] += r['count']
        b['ib'] += float(r['ib'] or 0)
        b['gc'] += float(r['gc'] or 0)
    return [dict(label=k, **v)
            for k, v in sorted(bucket.items(), key=lambda kv: -kv[1]['count'])]


def _rows_param(key: str) -> Callable:
    """Build a row builder for a ``service_params`` JSON key (Python-side)."""
    def builder(qs, _gran=None):
        bucket: dict[str, dict] = {}
        for r in qs.values('service_params', 'channel',
                           'budget_amount', 'quote_amount'):
            sp = r['service_params'] if isinstance(r['service_params'], dict) else {}
            k = (str(sp.get(key, '')).strip() or '—')
            b = bucket.setdefault(k, {'count': 0, 'ib': 0.0, 'gc': 0.0})
            b['count'] += 1
            if r['channel'] == 'IBTIKAR':
                b['ib'] += float(r['budget_amount'] or 0)
            elif r['channel'] == 'GENOCLAB':
                b['gc'] += float(r['quote_amount'] or 0)
        return [dict(label=k, **v)
                for k, v in sorted(bucket.items(), key=lambda kv: -kv[1]['count'])]
    return builder


def _rows_period(qs, gran='month'):
    trunc = {'month': TruncMonth, 'quarter': TruncQuarter,
             'year': TruncYear}.get(gran, TruncMonth)('created_at')
    rows = (qs.annotate(p=trunc).values('p')
              .annotate(**_amount_annots()).order_by('p'))
    out = []
    for r in rows:
        p = r['p']
        if p is None:
            label = '—'
        elif gran == 'quarter':
            label = f"{p.year}-T{(p.month - 1) // 3 + 1}"
        elif gran == 'year':
            label = str(p.year)
        else:
            label = p.strftime('%Y-%m')
        out.append({'label': label, 'count': r['count'],
                    'ib': float(r['ib'] or 0), 'gc': float(r['gc'] or 0)})
    return out


# ---------------------------------------------------------------------------
# Available dimensions — the menu the admin configures the bilan from
# ---------------------------------------------------------------------------

def _label_maps():
    from core.models import Request
    from accounts.models import User
    return {
        'status': dict(Request.STATUS_CHOICES),
        'channel': {'IBTIKAR': 'IBTIKAR', 'GENOCLAB': 'GENOCLAB'},
        'wilaya': dict(User.WILAYA_CHOICES),
        'gender': dict(User.GENDER_CHOICES),
    }


def _dimensions() -> dict:
    """Ordered registry: section key -> (title, row-builder)."""
    maps = _label_maps()
    return {
        'by_channel':        ("Par canal",
                              lambda qs, g=None: _rows_db(qs, 'channel', maps['channel'])),
        'by_period':         ("Par période", _rows_period),
        'by_service':        ("Par service", _rows_service),
        'by_service_type':   ("Par type de service",
                              lambda qs, g=None: _rows_db(qs, 'service__service_type')),
        'by_category':       ("Par nature / plateforme", _rows_category),
        'by_analysis_mode':  ("Par type d'analyse", _rows_param('analysis_mode')),
        'by_analysis_frame': ("Par cadre de l'analyse", _rows_param('analysis_frame')),
        'by_organism_type':  ("Par type d'échantillon", _rows_param('organism_type')),
        'by_status':         ("Par statut",
                              lambda qs, g=None: _rows_db(qs, 'status', maps['status'])),
        'by_organization':   ("Par établissement",
                              lambda qs, g=None: _rows_db(qs, 'requester__organization')),
        'by_wilaya':         ("Par wilaya",
                              lambda qs, g=None: _rows_db(qs, 'requester__wilaya', maps['wilaya'], empty='—')),
        'by_gender':         ("Par genre",
                              lambda qs, g=None: _rows_db(qs, 'requester__gender', maps['gender'], empty='—')),
    }


def available_sections() -> list[tuple[str, str]]:
    """[(key, title)] for the admin configuration UI, in display order."""
    return [(k, v[0]) for k, v in _dimensions().items()]


# Sensible default selection when the admin doesn't pick.
DEFAULT_SECTIONS = [
    'by_channel', 'by_period', 'by_service', 'by_category',
    'by_organization', 'by_wilaya', 'by_gender', 'by_status',
]

_COLUMNS = ['Libellé', 'Nombre', 'Part (%)',
            'Montant IBTIKAR (DA)', 'Montant GENOCLAB (DA)', 'Montant total (DA)']


def _assemble(key: str, title: str, rows: list[dict]) -> dict:
    grand = sum(r['count'] for r in rows) or 0
    tib = tgc = 0.0
    out_rows = []
    for r in rows:
        total = r['ib'] + r['gc']
        pct = round(r['count'] / grand * 100, 1) if grand else 0.0
        out_rows.append([r['label'], r['count'], pct, r['ib'], r['gc'], total])
        tib += r['ib']
        tgc += r['gc']
    total_row = ['Total', grand, 100.0 if grand else 0.0, tib, tgc, tib + tgc]
    return {'key': key, 'title': title, 'columns': list(_COLUMNS),
            'rows': out_rows, 'total_row': total_row}


def build_bilan(filters: dict, sections: list[str] | None = None,
                granularity: str = 'month') -> dict:
    """Assemble the configured activity report.

    ``filters``     : the same kwargs accepted by ``core.stats._apply_filters``.
    ``sections``    : ordered list of dimension keys (see ``available_sections``).
    ``granularity`` : 'month' | 'quarter' | 'year' for the period section.
    """
    from core.models import Request

    sections = [s for s in (sections or DEFAULT_SECTIONS) if s in _dimensions()]
    if not sections:
        sections = list(DEFAULT_SECTIONS)

    qs = _apply_filters(Request.objects.all(), **filters)
    dims = _dimensions()

    built = []
    for key in sections:
        title, builder = dims[key]
        rows = builder(qs, granularity)
        built.append(_assemble(key, title, rows))

    return {
        'kpis': headline_kpis(**filters),
        'sections': built,
        'granularity': granularity,
        'total_requests': qs.count(),
    }
