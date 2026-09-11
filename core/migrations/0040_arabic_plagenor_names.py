from django.db import migrations


def forwards(apps, schema_editor):
    Content = apps.get_model('core', 'PlatformContent')
    for entry in Content.objects.using(schema_editor.connection.alias).filter(lang='ar', value__contains='PLAGENOR'):
        entry.value = (entry.value
            .replace('PLAGENOR 4.0', 'بلاجينور 4.0')
            .replace('PLAGENOR هي الأرضية التكنولوجية للجينوميك', 'الأرضية التكنولوجية للجينوميك')
            .replace('PLAGENOR — الأرضية التكنولوجية للجينوميك', 'الأرضية التكنولوجية للجينوميك')
            .replace('منصة PLAGENOR', 'الأرضية التكنولوجية للجينوميك')
            .replace('PLAGENOR', 'الأرضية التكنولوجية للجينوميك'))
        entry.save(using=schema_editor.connection.alias, update_fields=['value'])


class Migration(migrations.Migration):
    dependencies = [('core', '0039_request_appointment_note_request_appointment_time')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
