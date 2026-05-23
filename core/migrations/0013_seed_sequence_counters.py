"""Seed SequenceCounter rows from the high-water mark of existing IDs.

Without this, the first allocation after the migration would start at 1 and
collide with legacy display_ids / invoice_numbers already in the database.
"""
from django.db import migrations


PREFIXES = (
    ('IBK',),      # registered IBTIKAR submissions
    ('GCL',),      # GENOCLAB (registered + guest share the same prefix)
    ('IBT',),      # guest IBTIKAR submissions
)


def _max_suffix(rows, prefix, year):
    needle = f"{prefix}-{year}-"
    max_n = 0
    for did in rows:
        if not did or not did.startswith(needle):
            continue
        try:
            n = int(did.rsplit('-', 1)[-1])
        except ValueError:
            continue
        if n > max_n:
            max_n = n
    return max_n


def seed_counters(apps, schema_editor):
    SequenceCounter = apps.get_model('core', 'SequenceCounter')
    Request = apps.get_model('core', 'Request')
    Invoice = apps.get_model('core', 'Invoice')

    # Discover all years that have requests, then seed one counter per
    # (prefix, year) combination from the actual high-water mark of
    # existing display_ids.
    req_years = sorted({
        r.created_at.year for r in Request.objects.only('created_at').iterator()
        if r.created_at is not None
    })
    request_display_ids = list(Request.objects.values_list('display_id', flat=True))

    for year in req_years:
        for (prefix,) in PREFIXES:
            highest = _max_suffix(request_display_ids, prefix, year)
            if highest <= 0:
                continue
            SequenceCounter.objects.update_or_create(
                scope=f"{prefix}-{year}",
                defaults={'value': highest},
            )

    inv_years = sorted({
        i.created_at.year for i in Invoice.objects.only('created_at').iterator()
        if i.created_at is not None
    })
    invoice_numbers = list(Invoice.objects.values_list('invoice_number', flat=True))
    for year in inv_years:
        highest = _max_suffix(invoice_numbers, 'GCL-INV', year)
        if highest <= 0:
            continue
        SequenceCounter.objects.update_or_create(
            scope=f"GCL-INV-{year}",
            defaults={'value': highest},
        )


def noop(apps, schema_editor):
    """Reverse: leave counter values in place — they're harmless."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_sequencecounter'),
    ]

    operations = [
        migrations.RunPython(seed_counters, noop),
    ]
