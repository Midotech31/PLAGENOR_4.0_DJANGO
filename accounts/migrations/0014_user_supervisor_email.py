from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0013_user_ibtikar_balance_constraint')]

    operations = [
        migrations.AddField(
            model_name='user',
            name='supervisor_email',
            field=models.EmailField(
                blank=True, default='', max_length=254,
                verbose_name='Email du directeur de thèse / encadrant',
            ),
        ),
    ]
