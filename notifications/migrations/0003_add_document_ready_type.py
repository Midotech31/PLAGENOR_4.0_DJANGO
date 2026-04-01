# notifications/migrations/0003_add_document_ready_type.py

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_add_notification_deep_linking'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(
                choices=[
                    ('INFO', 'Info'),
                    ('WORKFLOW', 'Workflow'),
                    ('SYSTEM', 'System'),
                    ('ASSIGNMENT', 'Assignment'),
                    ('STATUS_CHANGE', 'Status Change'),
                    ('APPOINTMENT', 'Appointment'),
                    ('REPORT', 'Report Ready'),
                    ('PAYMENT', 'Payment'),
                    ('DOCUMENT_READY', 'Document Ready'),
                ],
                default='INFO',
                max_length=20
            ),
        ),
    ]
