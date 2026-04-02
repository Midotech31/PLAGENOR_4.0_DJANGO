# Generated migration for channel field on ServiceFormField

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0022_extend_serviceformfield'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviceformfield',
            name='channel',
            field=models.CharField(
                max_length=10,
                choices=[
                    ('IBTIKAR', 'IBTIKAR'),
                    ('GENOCLAB', 'GENOCLAB'),
                    ('BOTH', 'Les deux'),
                ],
                default='BOTH',
                help_text='Channel availability: IBTIKAR only, GENOCLAB only, or BOTH',
            ),
        ),
    ]
