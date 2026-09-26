# Generated for controlled PLAGENOR 2026 inventory review workflow.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erp', '0025_legacyinventoryrecord'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='legacyinventoryrecord',
            name='review_status',
            field=models.CharField(
                choices=[
                    ('OPEN', 'À traiter'),
                    ('CONFIRMED', 'Source vérifiée / donnée confirmée'),
                    ('CORRECTED', 'Correction reportée dans PLAGENOR'),
                    ('NOT_APPLICABLE', 'Non applicable / ne pas importer'),
                ],
                default='OPEN',
                max_length=16,
                verbose_name='État de la revue humaine',
            ),
        ),
        migrations.AddField(
            model_name='legacyinventoryrecord',
            name='review_note',
            field=models.TextField(blank=True, verbose_name='Conclusion de la revue humaine'),
        ),
        migrations.AddField(
            model_name='legacyinventoryrecord',
            name='reviewed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Date de revue'),
        ),
        migrations.AddField(
            model_name='legacyinventoryrecord',
            name='reviewed_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='+',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Revu par',
            ),
        ),
        migrations.AddIndex(
            model_name='legacyinventoryrecord',
            index=models.Index(
                fields=['resolution', 'review_status'],
                name='erp_legacyi_resolut_ef54f1_idx',
            ),
        ),
    ]
