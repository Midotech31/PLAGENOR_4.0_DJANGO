"""Back up and verify the first scientific-stock upgrade on existing Render data.

The encrypted dump and aggregate evidence remain in the existing private backup
storage. Existing ERP tables are locked against writes during the comparison;
PostgreSQL rolls back the upgrade if backup or preservation verification fails.
"""
import hashlib
import json
import os
import uuid

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')

import django

django.setup()

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

UPGRADE = ('erp', '0030_scientific_stock')


def manifest(models):
    result = {}
    for model in models:
        fields = [field.attname for field in model._meta.concrete_fields]
        digest = hashlib.sha256()
        count = 0
        for values in model.objects.order_by(model._meta.pk.attname).values_list(*fields).iterator(chunk_size=500):
            digest.update(json.dumps(values, default=str, ensure_ascii=False, sort_keys=True,
                separators=(',', ':')).encode('utf-8') + b'\n')
            count += 1
        result[model._meta.label_lower] = {'fields': fields, 'rows': count, 'sha256': digest.hexdigest()}
    return result


def migrate_safely(*, backup=None, storage=None):
    applied = MigrationRecorder(connection).applied_migrations()
    erp_applied = sorted(node for node in applied if node[0] == 'erp')
    if connection.vendor != 'postgresql' or not os.getenv('RENDER_GIT_COMMIT') or not erp_applied or UPGRADE in applied:
        call_command('migrate', interactive=False)
        return None
    from scripts.production_inventory_bootstrap import _backup_database
    backup = backup or _backup_database
    storage = storage or default_storage
    executor = MigrationExecutor(connection)
    apps = executor.loader.project_state([erp_applied[-1]]).apps
    models = sorted(apps.get_app_config('erp').get_models(include_auto_created=True), key=lambda model: model._meta.db_table)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '15s'")
            names = ', '.join(connection.ops.quote_name(model._meta.db_table) for model in models)
            cursor.execute('LOCK TABLE ' + names + ' IN SHARE ROW EXCLUSIVE MODE')
        before = manifest(models)
        metadata = backup()
        if not metadata.get('backup_object', '').startswith('database_backups/') or not metadata.get('plaintext_bytes'):
            raise RuntimeError('The scientific-stock upgrade requires a verified private database backup.')
        call_command('migrate', interactive=False)
        after = manifest(models)
        if after != before:
            raise RuntimeError('Existing ERP data changed during the scientific-stock upgrade; PostgreSQL rolled it back.')
        evidence = {'status': 'verified', 'commit': os.getenv('RENDER_GIT_COMMIT'),
            'backup': metadata, 'source_migration': erp_applied[-1][1], 'tables': after}
        name = 'database_backups/scientific-stock-upgrade-' + str(uuid.uuid4()) + '.json'
        saved = storage.save(name, ContentFile(json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode()))
        if not storage.exists(saved):
            raise RuntimeError('Scientific-stock preservation evidence was not persisted.')
    print(json.dumps({'event': 'scientific_stock_upgrade_verified', 'evidence_object': saved,
        'backup_object': metadata['backup_object'], 'tables': len(after),
        'rows': sum(row['rows'] for row in after.values()), 'commit': evidence['commit']}, sort_keys=True))
    return evidence


if __name__ == '__main__':
    migrate_safely()
