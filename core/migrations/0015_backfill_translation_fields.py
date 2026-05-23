"""Phase 3.4 backfill — copy existing legacy `name` / `description` etc.
into the new `<field>_fr` columns introduced by django-modeltranslation.

Without this, the per-language columns are NULL for legacy data, and
``service.name`` would silently fall back to whatever the original
column still holds — readable today, but the moment an admin saves a
Service in the admin (which writes the modeltranslation per-language
columns) the un-backfilled French row would appear blank in fr locale.

We populate ONLY empty per-language fields and use the historical apps
registry so modeltranslation's descriptor is bypassed — ``obj.name``
here reads the original physical column, ``obj.name_fr`` reads the new
one. Idempotent and safely re-runnable.
"""
from django.db import migrations


TARGETS = [
    ('core', 'Service', ['name', 'description']),
    ('core', 'ServicePricing', ['name', 'description']),
    ('core', 'ServiceFormField', ['label']),
    ('accounts', 'Technique', ['name', 'category']),
]


def backfill(apps, schema_editor):
    for app_label, model_name, fields in TARGETS:
        Model = apps.get_model(app_label, model_name)
        for obj in Model.objects.all().iterator():
            updates = []
            for field in fields:
                original = getattr(obj, field, None)
                fr_attr = f"{field}_fr"
                current_fr = getattr(obj, fr_attr, None)
                if original and not current_fr:
                    setattr(obj, fr_attr, original)
                    updates.append(fr_attr)
            if updates:
                obj.save(update_fields=updates)


def noop(apps, schema_editor):
    """Reverse: leave the per-language columns populated. The original
    column still holds the same values, so nothing breaks."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_service_description_ar_service_description_en_and_more'),
        ('accounts', '0007_technique_category_ar_technique_category_en_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
