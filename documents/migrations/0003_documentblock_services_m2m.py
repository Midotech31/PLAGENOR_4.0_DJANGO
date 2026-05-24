"""Convert DocumentBlock.service (FK) → DocumentBlock.services (M2M).

The old single-service ForeignKey forced admins to duplicate a block
once per target service when scoping to a curated subset
(e.g. "applies to PCR + Seq02 + Lyoph"). The M2M lets one block carry
the whole list, eliminating the drift risk where copies of the same
block fall out of sync.

Order of operations matters: we add the new M2M first, copy each
existing row's ``service_id`` into the M2M through-table, then drop
the old FK. Running it the other way would lose data.
"""
from django.db import migrations, models


def copy_fk_to_m2m(apps, schema_editor):
    DocumentBlock = apps.get_model('documents', 'DocumentBlock')
    for block in DocumentBlock.objects.all():
        if block.service_id:
            block.services.add(block.service_id)


def copy_m2m_to_fk(apps, schema_editor):
    """Reverse: take the first service from the M2M (if any) and put it on
    the FK. Multi-service blocks lose all but the first service; that's
    the expected lossy-reverse contract — admins should clone the block
    before reverting if they need to preserve subsets."""
    DocumentBlock = apps.get_model('documents', 'DocumentBlock')
    for block in DocumentBlock.objects.all():
        first = block.services.order_by('pk').first()
        block.service = first
        block.save(update_fields=['service'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
        ('documents', '0002_documentblock'),
    ]

    operations = [
        # 1) Add the new M2M field — coexists with the old FK during data copy.
        migrations.AddField(
            model_name='documentblock',
            name='services',
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "Laissez vide pour appliquer à tous les services (bloc global). "
                    "Sélectionnez un ou plusieurs services pour limiter le bloc à ce sous-ensemble."
                ),
                related_name='document_blocks_new',
                to='core.service',
                verbose_name='Services concernés',
            ),
        ),
        # 2) Copy each block's old single service into the new M2M.
        migrations.RunPython(copy_fk_to_m2m, copy_m2m_to_fk),
        # 3) Drop the index that referenced the old FK.
        migrations.RemoveIndex(
            model_name='documentblock',
            name='document_bl_templat_c6a16b_idx',
        ),
        # 4) Drop the old FK now that data is safely in the M2M.
        migrations.RemoveField(
            model_name='documentblock',
            name='service',
        ),
        # 5) Rename the M2M reverse accessor to the final name (was suffixed
        #    with _new to avoid clashing with the FK's related_name during
        #    the overlap window above).
        migrations.AlterField(
            model_name='documentblock',
            name='services',
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "Laissez vide pour appliquer à tous les services (bloc global). "
                    "Sélectionnez un ou plusieurs services pour limiter le bloc à ce sous-ensemble."
                ),
                related_name='document_blocks',
                to='core.service',
                verbose_name='Services concernés',
            ),
        ),
        # 6) Add the leaner index — services is M2M so it can't be part of
        #    a composite index; the queryset hits the M2M via a JOIN anyway.
        migrations.AddIndex(
            model_name='documentblock',
            index=models.Index(
                fields=['template_type', 'language', 'is_active'],
                name='document_bl_templat_f352e4_idx',
            ),
        ),
    ]
