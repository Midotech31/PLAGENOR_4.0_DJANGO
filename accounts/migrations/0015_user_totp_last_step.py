from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0014_user_supervisor_email')]
    operations = [migrations.AddField(
        model_name='user', name='totp_last_step',
        field=models.BigIntegerField(blank=True, editable=False, null=True),
    )]
