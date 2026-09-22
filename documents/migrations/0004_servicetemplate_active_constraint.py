from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0003_documentblock_services_m2m'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='servicetemplate',
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name='servicetemplate',
            constraint=models.UniqueConstraint(
                fields=('service', 'template_type'),
                condition=models.Q(is_active=True),
                name='unique_active_service_template',
            ),
        ),
    ]
