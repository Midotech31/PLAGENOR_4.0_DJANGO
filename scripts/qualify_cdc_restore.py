#!/usr/bin/env python3
"""Exercise native CDC recovery in the two explicitly named, local CI databases."""
import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')

import django

django.setup()

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import serializers
from django.core.files.uploadedfile import SimpleUploadedFile

from erp.cdc.lot_catalog import fingerprint
from erp.models import CdcItem, CdcRevision
from erp.services.cdc import create_dossier, save_cdc_item, save_criterion, save_requirement
from erp.services.cdc_exchange import apply_workbook
from erp.services.cdc_finance import export_financial, financial_snapshot, preview_financial
from erp.services.cdc_reuse import apply_reuse, preview_reuse, source_rows

MODELS = ('WorkItem', 'CdcDossier', 'CdcLot', 'CdcItem', 'CdcRevision',
          'CdcRequirement', 'CdcCriterion', 'CdcWorkbookPreview', 'CdcReusePreview', 'AuditEvent')


def guard_database(mode):
    config = settings.DATABASES['default']
    expected = 'plagenor_ci' if mode == 'seed' else 'plagenor_restore_ci'
    if (os.environ.get('CI') != 'true' or config['ENGINE'] != 'django.db.backends.postgresql'
            or config['HOST'] != '127.0.0.1' or config['NAME'] != expected):
        raise SystemExit('CDC restore qualification is restricted to its two local CI databases.')


def manifest():
    result = {}
    for name in MODELS:
        records = apps.get_model('erp', name).objects.order_by('pk')
        rows = json.loads(serializers.serialize('json', records))
        raw = json.dumps(rows, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        result[name] = {'count': len(rows), 'sha256': hashlib.sha256(raw).hexdigest()}
    for revision in CdcRevision.objects.all():
        if fingerprint({'document': revision.data, 'estimates': revision.estimates}) != revision.sha256:
            raise SystemExit('A restored CDC revision failed its integrity check.')
    return result


def seed(path):
    actor = get_user_model().objects.create_user(username='ci-cdc-restore', password=None, role='PLATFORM_ADMIN')
    dossiers = []
    for index, family in enumerate(('equipment', 'reagents', 'works'), 1):
        dossier = create_dossier(actor, family=family, reference=f'{9900+index}/SME/SDFM/SG/ESSBO/2026',
            title=f'SYNTHETIC CDC restore qualification — {family}')
        item = dossier.lots.first().items.first()
        save_cdc_item(actor, item.lot_id, expected=dossier.version, pk=item.pk,
            values={'quantity': 2, 'estimated_price': '123.45', 'tax_rate': 19,
                    'price_source': 'SYNTHETIC estimate'}, reason='SYNTHETIC budget fixture')
        dossier.refresh_from_db()
        save_requirement(actor, item.pk, expected=dossier.version, values={'position': 1, 'kind': 'MANDATORY',
            'statement': 'SYNTHETIC acceptance requirement', 'evidence': 'SYNTHETIC technical sheet',
            'verification_method': 'SYNTHETIC receipt check'}, reason='SYNTHETIC requirement')
        dossier.refresh_from_db()
        save_criterion(actor, dossier.pk, expected=dossier.version, values={'code': 'TECH',
            'title': 'SYNTHETIC technical criterion', 'method': 'BINARY', 'weight': 100,
            'position': 1, 'evidence': 'SYNTHETIC evidence'}, reason='SYNTHETIC criterion')
        dossier.refresh_from_db()
        dossiers.append(dossier)
    equipment, reagents, _works = dossiers
    revision, rows = source_rows(actor, equipment.revisions.first().pk, equipment.family)
    reuse = preview_reuse(actor, equipment.pk, expected=equipment.version, source_revision=revision.pk,
        target_lot=equipment.lots.first().pk, selections=[rows[0]['selection']], reason='SYNTHETIC pending copy')
    finance = preview_financial(actor, reagents.pk, expected=reagents.version,
        upload=SimpleUploadedFile('budget.xlsx', export_financial(actor, reagents)), reason='SYNTHETIC pending import')
    path.write_text(json.dumps({'actor': str(actor.pk), 'reuse': str(reuse.pk), 'finance': str(finance.pk),
        'manifest': manifest()}, indent=2))
    print('Synthetic CDC recovery fixture created in the local CI database.')


def verify(path):
    expected = json.loads(path.read_text())
    actual = manifest()
    if actual != expected['manifest']:
        raise SystemExit('CDC counts or content differ after PostgreSQL restoration.')
    actor = get_user_model().objects.get(pk=expected['actor'])
    preview = apps.get_model('erp', 'CdcReusePreview').objects.get(pk=expected['reuse'])
    rows = [{key: value for key, value in row.items() if key in
        {'selection', 'designation', 'specifications', 'unit', 'packaging', 'quantity', 'details'}}
        for row in preview.payload['rows']]
    reused = apply_reuse(actor, preview.pk, rows=rows)
    imported = apply_workbook(actor, expected['finance'])
    if apply_reuse(actor, preview.pk, rows=rows).pk != reused.pk:
        raise SystemExit('Restored copy preview is not idempotent.')
    if apply_workbook(actor, expected['finance']).pk != imported.pk:
        raise SystemExit('Restored financial preview is not idempotent.')
    copied = CdcItem.objects.get(lot=preview.target_lot, source_key__startswith='new-')
    if copied.estimated_price is not None or copied.requirements.count() != 1:
        raise SystemExit('Restored copy lost its requirements or reused historical prices.')
    _, summary = financial_snapshot(imported.dossier)
    if str(summary['currencies']['DZD']['gross']) != '293.81':
        raise SystemExit('Restored financial totals differ from the synthetic fixture.')
    manifest()
    evidence = {'status': 'PASS', 'scope': 'SYNTHETIC_CI_DATABASE_ONLY', 'models': actual,
        'restored_previews_confirmed': 2, 'idempotent_retries': 2,
        'historical_prices_excluded_from_copy': True, 'financial_total_ttc': '293.81'}
    path.with_name('cdc-restore-evidence.json').write_text(json.dumps(evidence, indent=2))
    print('CDC restore PASS: data, immutable revisions, preview confirmation, retry and financial totals.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('seed', 'verify'))
    parser.add_argument('evidence', type=Path)
    args = parser.parse_args()
    guard_database(args.mode)
    (seed if args.mode == 'seed' else verify)(args.evidence)
