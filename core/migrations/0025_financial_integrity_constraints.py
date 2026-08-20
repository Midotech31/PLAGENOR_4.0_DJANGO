from django.db import migrations, models
from django.db.models import F, Q


def normalize_and_validate_financial_rows(apps, schema_editor):
    """Normalize the documented legacy discount sign, reject other corruption.

    Older pricing code accepted discounts stored as negative numbers. The
    calculation already applies discounts with ``-abs(amount)``, so converting
    only those rows to a positive magnitude preserves totals exactly. Any other
    invalid financial row is ambiguous and intentionally stops the migration
    for operator review instead of silently changing an invoice.
    """
    ServicePricing = apps.get_model('core', 'ServicePricing')
    Invoice = apps.get_model('core', 'Invoice')
    Request = apps.get_model('core', 'Request')

    for tier in ServicePricing.objects.filter(
            pricing_type='DISCOUNT', amount__lt=0):
        tier.amount = abs(tier.amount)
        tier.save(update_fields=['amount'])

    invalid_tiers = ServicePricing.objects.filter(
        Q(amount__lt=0)
        | Q(min_quantity__lt=1)
        | (Q(max_quantity__isnull=False) & Q(max_quantity__lt=F('min_quantity')))
        | Q(min_amount__lt=0)
        | Q(max_amount__lt=0)
        | (Q(min_amount__isnull=False) & Q(max_amount__isnull=False)
           & Q(max_amount__lt=F('min_amount')))
    )
    if invalid_tiers.exists():
        raise RuntimeError(
            'Invalid legacy ServicePricing rows must be reviewed before '
            'financial constraints can be installed: '
            f'{list(invalid_tiers.values_list("pk", flat=True)[:20])}')

    invalid_invoices = Invoice.objects.filter(
        Q(subtotal_ht__lt=0)
        | Q(vat_rate__lt=0)
        | Q(vat_rate__gt=1)
        | Q(vat_amount__lt=0)
        | Q(total_ttc__lt=0)
    )
    if invalid_invoices.exists():
        raise RuntimeError(
            'Invalid legacy invoices must be reviewed before financial '
            'constraints can be installed: '
            f'{list(invalid_invoices.values_list("invoice_number", flat=True)[:20])}')

    invalid_requests = Request.objects.filter(
        Q(budget_amount__lt=0)
        | Q(declared_ibtikar_balance__lt=0)
        | Q(quote_amount__lt=0)
        | Q(admin_validated_price__lt=0)
    )
    if invalid_requests.exists():
        raise RuntimeError(
            'Invalid legacy request financial values must be reviewed before '
            'constraints can be installed: '
            f'{list(invalid_requests.values_list("display_id", flat=True)[:20])}')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0024_request_payment_verification_note_and_more'),
    ]

    operations = [
        migrations.RunPython(
            normalize_and_validate_financial_rows,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='request',
            constraint=models.CheckConstraint(
                condition=Q(budget_amount__gte=0),
                name='request_budget_amount_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='request',
            constraint=models.CheckConstraint(
                condition=Q(declared_ibtikar_balance__gte=0),
                name='request_declared_balance_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='request',
            constraint=models.CheckConstraint(
                condition=Q(quote_amount__gte=0),
                name='request_quote_amount_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='request',
            constraint=models.CheckConstraint(
                condition=(Q(admin_validated_price__isnull=True)
                           | Q(admin_validated_price__gte=0)),
                name='request_admin_price_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='servicepricing',
            constraint=models.CheckConstraint(
                condition=Q(amount__gte=0),
                name='service_pricing_amount_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='servicepricing',
            constraint=models.CheckConstraint(
                condition=Q(min_quantity__gte=1),
                name='service_pricing_min_quantity_positive'),
        ),
        migrations.AddConstraint(
            model_name='servicepricing',
            constraint=models.CheckConstraint(
                condition=(Q(max_quantity__isnull=True)
                           | Q(max_quantity__gte=F('min_quantity'))),
                name='service_pricing_quantity_range_valid'),
        ),
        migrations.AddConstraint(
            model_name='servicepricing',
            constraint=models.CheckConstraint(
                condition=(Q(min_amount__isnull=True) | Q(min_amount__gte=0)),
                name='service_pricing_min_amount_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='servicepricing',
            constraint=models.CheckConstraint(
                condition=(Q(max_amount__isnull=True) | Q(max_amount__gte=0)),
                name='service_pricing_max_amount_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='servicepricing',
            constraint=models.CheckConstraint(
                condition=(Q(min_amount__isnull=True)
                           | Q(max_amount__isnull=True)
                           | Q(max_amount__gte=F('min_amount'))),
                name='service_pricing_amount_range_valid'),
        ),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(
                condition=Q(subtotal_ht__gte=0),
                name='invoice_subtotal_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(
                condition=Q(vat_rate__gte=0) & Q(vat_rate__lte=1),
                name='invoice_vat_rate_valid'),
        ),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(
                condition=Q(vat_amount__gte=0),
                name='invoice_vat_amount_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(
                condition=Q(total_ttc__gte=0),
                name='invoice_total_nonnegative'),
        ),
    ]
