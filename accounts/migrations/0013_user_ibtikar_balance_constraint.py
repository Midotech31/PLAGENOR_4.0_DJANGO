from django.db import migrations, models
from django.db.models import Q


def validate_legacy_balances(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    invalid = User.objects.filter(ibtikar_declared_balance__lt=0)
    if invalid.exists():
        raise RuntimeError(
            'Negative legacy IBTIKAR balances require operator review before '
            'the integrity constraint can be installed: '
            f'{list(invalid.values_list("pk", flat=True)[:20])}')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_alter_user_totp_secret'),
    ]

    operations = [
        migrations.RunPython(validate_legacy_balances, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.CheckConstraint(
                condition=(Q(ibtikar_declared_balance__isnull=True)
                           | Q(ibtikar_declared_balance__gte=0)),
                name='user_ibtikar_balance_nonnegative'),
        ),
    ]
