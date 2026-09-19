from django.db import migrations


def clear_existing_mfa(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.all().update(
        totp_enabled=False,
        totp_secret='',
        totp_last_step=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_user_totp_last_step'),
    ]

    operations = [
        migrations.RunPython(
            clear_existing_mfa,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
