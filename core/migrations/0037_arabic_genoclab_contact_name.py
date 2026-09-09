from django.db import migrations


def forwards(apps, schema_editor):
    Content = apps.get_model('core', 'PlatformContent')
    Content.objects.using(schema_editor.connection.alias).update_or_create(
        key='genoclab_contact_name', lang='ar',
        defaults={'value': 'الدكتورة بودربالة هاجر'},
    )


class Migration(migrations.Migration):
    dependencies = [('core', '0036_public_postal_address')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
