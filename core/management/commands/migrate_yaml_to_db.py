"""
One-time migration of service field definitions from YAML registry to DB (ServiceFormField).

Usage: python manage.py migrate_yaml_to_db [--dry-run]

This command reads all YAML service definition files and creates ServiceFormField
entries for each service's parameters and sample_table columns.

Only creates NEW entries — existing DB entries are skipped.
Use --dry-run to preview without writing.
"""
import re
from django.core.management.base import BaseCommand
from django.db import transaction

from core.registry import load_service_registry, _load_registry_from_disk
from core.models import Service, ServiceFormField


# Map YAML field types to DB field types
YAML_TYPE_TO_DB = {
    'string': 'text',
    'text': 'textarea',
    'enum': 'select',
    'boolean': 'boolean',
    'integer': 'number',
    'float': 'number',
}


def _parse_bilingual_label(label):
    """Split a label into FR and EN parts if possible."""
    if not label:
        return '', ''
    # Common pattern: "French label / English label"
    if ' / ' in label:
        parts = label.split(' / ', 1)
        return parts[0].strip(), parts[1].strip()
    # Pattern: "French (English)" or "French — English"
    if ' (' in label or ' — ' in label:
        m = re.match(r'^(.+?)\s*[(—]\s*(.+?)\s*[)]$', label)
        if m:
            return m.group(1).strip(), m.group(2).strip()
    return label, ''


def _normalize_key(name):
    """Make a safe key from field name."""
    return re.sub(r'[^a-z0-9_]', '_', name.lower().replace(' ', '_'))


def migrate_service(service_code, dry_run=False):
    """Migrate one service's YAML fields to DB."""
    definition = load_service_registry().get(service_code)
    if not definition:
        return 0, 0, f"  SKIP — no YAML for {service_code}"

    try:
        service = Service.objects.get(code=service_code)
    except Service.DoesNotExist:
        return 0, 0, f"  SKIP — service {service_code} not in DB"

    params_created = 0
    samples_created = 0

    # ---- Migrate parameters ----
    parameters = definition.get('parameters', [])
    for i, param in enumerate(parameters):
        key = param.get('name', '')
        if not key:
            continue

        yaml_label = param.get('label', key)
        label_fr, label_en = _parse_bilingual_label(yaml_label)

        yaml_type = param.get('type', 'text')
        db_type = YAML_TYPE_TO_DB.get(yaml_type, 'text')

        yaml_options = param.get('options', [])
        yaml_required = param.get('required', False)
        yaml_help = param.get('help', '')

        # Skip if already exists
        if ServiceFormField.objects.filter(service=service, name=key, field_category='parameter').exists():
            continue

        field = ServiceFormField(
            service=service,
            name=key,
            label=yaml_label,
            label_fr=label_fr or yaml_label,
            label_en=label_en,
            field_type=db_type,
            field_category='parameter',
            options=yaml_options if yaml_options else [],
            is_required=yaml_required,
            required=yaml_required,
            help_text_fr=yaml_help,
            order=i,
        )
        if not dry_run:
            field.save()
        params_created += 1

    # ---- Migrate sample_table columns ----
    sample_table = definition.get('sample_table', {})
    columns = sample_table.get('columns', [])
    for i, col in enumerate(columns):
        key = col.get('name', '')
        if not key:
            continue

        yaml_label = col.get('label', key)
        label_fr, label_en = _parse_bilingual_label(yaml_label)

        yaml_type = col.get('type', 'text')
        db_type = YAML_TYPE_TO_DB.get(yaml_type, 'text')
        yaml_options = col.get('options', [])

        # Skip if already exists
        if ServiceFormField.objects.filter(service=service, name=key, field_category='sample_table').exists():
            continue

        field = ServiceFormField(
            service=service,
            name=key,
            label=yaml_label,
            label_fr=label_fr or yaml_label,
            label_en=label_en,
            field_type=db_type,
            field_category='sample_table',
            options=yaml_options if yaml_options else [],
            is_required=col.get('required', False),
            required=col.get('required', False),
            order=i,
        )
        if not dry_run:
            field.save()
        samples_created += 1

    return params_created, samples_created, ''


class Command(BaseCommand):
    help = 'Migrate service field definitions from YAML registry to ServiceFormField DB'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Show what would be created without writing to DB',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Delete all existing ServiceFormField entries before migrating (WARNING: destructive)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        # Clear registry cache to pick up latest YAML files
        try:
            from core.registry import _load_registry_from_disk
            _load_registry_from_disk.cache_clear()
        except Exception:
            pass

        if force and not dry_run:
            confirm = input('This will DELETE all existing ServiceFormField entries. Are you sure? [y/N]: ')
            if confirm.lower() != 'y':
                self.stdout.write(self.style.WARNING('Aborted.'))
                return

        if force:
            count = ServiceFormField.objects.count()
            if dry_run:
                self.stdout.write(f'  [dry-run] Would delete {count} existing ServiceFormField entries')
            else:
                ServiceFormField.objects.all().delete()
                self.stdout.write(self.style.WARNING(f'  Deleted {count} existing entries'))

        all_services = [s.code for s in Service.objects.all()]
        total_params = 0
        total_samples = 0

        self.stdout.write('\nMigrating service fields YAML -> DB\n')
        self.stdout.write(f"{'Service':<40} {'Params':>7} {'Samples':>8} {'Status'}")
        self.stdout.write('-' * 70)

        for code in sorted(all_services):
            params, samples, msg = migrate_service(code, dry_run=dry_run)
            total_params += params
            total_samples += samples
            status = 'CREATED' if params or samples else 'skipped'
            self.stdout.write(f'{code:<40} {params:>7} {samples:>8}  {status}')
            if msg:
                self.stdout.write(self.style.WARNING(msg))

        self.stdout.write('-' * 70)
        self.stdout.write(f"{'TOTAL':<40} {total_params:>7} {total_samples:>8}")

        if dry_run:
            self.stdout.write(self.style.WARNING('\n  [dry-run] No changes written. Run without --dry-run to apply.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n  Done. {total_params} parameters + {total_samples} sample columns created.'))

        # Verify counts per service
        if not dry_run:
            self.stdout.write('\nVerification:\n')
            self.stdout.write(f"{'Service':<40} {'parameter':>10} {'sample_table':>12}")
            self.stdout.write('-' * 64)
            for svc in Service.objects.all():
                p = ServiceFormField.objects.filter(service=svc, field_category='parameter').count()
                s = ServiceFormField.objects.filter(service=svc, field_category='sample_table').count()
                self.stdout.write(f'{svc.code:<40} {p:>10} {s:>12}')
