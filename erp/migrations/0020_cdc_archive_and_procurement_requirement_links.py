from decimal import Decimal
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('erp', '0019_cdc_workbook_and_reusable_lots'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(model_name='cdcdossier', name='archive_reason', field=models.CharField(blank=True, editable=False, max_length=500)),
        migrations.AddField(model_name='cdcdossier', name='archived_at', field=models.DateTimeField(blank=True, editable=False, null=True)),
        migrations.AddField(model_name='cdcdossier', name='archived_by', field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
        migrations.CreateModel(name='ProcurementRequirementLink', fields=[
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('shortage_quantity', models.DecimalField(decimal_places=6, max_digits=18)),
            ('purchase_quantity', models.DecimalField(decimal_places=6, max_digits=18)),
            ('reason', models.CharField(max_length=500)),
            ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ('line', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='requirement_links', to='erp.procurementline')),
            ('requirement', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='procurement_links', to='erp.runrequirement')),
        ]),
        migrations.AddConstraint(model_name='procurementrequirementlink', constraint=models.UniqueConstraint(fields=('line','requirement'), name='erp_plan_requirement_unique')),
        migrations.AddConstraint(model_name='procurementrequirementlink', constraint=models.CheckConstraint(condition=models.Q(shortage_quantity__gt=0, shortage_quantity__lte=Decimal('999999999999.999999')), name='erp_plan_requirement_shortage')),
        migrations.AddConstraint(model_name='procurementrequirementlink', constraint=models.CheckConstraint(condition=models.Q(purchase_quantity__gt=0, purchase_quantity__lte=Decimal('999999999999.999999')), name='erp_plan_requirement_purchase')),
    ]
