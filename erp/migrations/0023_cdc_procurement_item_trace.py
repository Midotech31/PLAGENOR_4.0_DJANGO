from decimal import Decimal
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('erp', '0022_cdc_review_capabilities'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='cdcitem',
            name='estimate_supplier',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='cdc_estimates', to='erp.party', verbose_name='Fournisseur de référence'),
        ),
        migrations.CreateModel(
            name='ProcurementCdcItemLink',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('required_quantity', models.DecimalField(decimal_places=6, max_digits=18)),
                ('stock_covered_quantity', models.DecimalField(decimal_places=6, default=0, max_digits=18)),
                ('shortage_quantity', models.DecimalField(decimal_places=6, max_digits=18)),
                ('reason', models.CharField(max_length=500)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='procurement_links', to='erp.cdcitem')),
                ('line', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cdc_item_links', to='erp.procurementline')),
            ],
        ),
        migrations.AddConstraint(
            model_name='procurementcdcitemlink',
            constraint=models.UniqueConstraint(fields=('line', 'item'), name='erp_plan_cdc_item_unique'),
        ),
        migrations.AddConstraint(
            model_name='procurementcdcitemlink',
            constraint=models.CheckConstraint(condition=models.Q(required_quantity__gt=0, required_quantity__lte=Decimal('999999999999.999999')), name='erp_plan_cdc_required'),
        ),
        migrations.AddConstraint(
            model_name='procurementcdcitemlink',
            constraint=models.CheckConstraint(condition=models.Q(stock_covered_quantity__gte=0, stock_covered_quantity__lte=Decimal('999999999999.999999')), name='erp_plan_cdc_covered'),
        ),
        migrations.AddConstraint(
            model_name='procurementcdcitemlink',
            constraint=models.CheckConstraint(condition=models.Q(shortage_quantity__gt=0, shortage_quantity__lte=Decimal('999999999999.999999')), name='erp_plan_cdc_shortage'),
        ),
        migrations.AddConstraint(
            model_name='procurementcdcitemlink',
            constraint=models.CheckConstraint(condition=models.Q(required_quantity=models.F('stock_covered_quantity') + models.F('shortage_quantity')), name='erp_plan_cdc_balance'),
        ),
    ]
