from django.db import migrations

CONTACTS = {'fr': {'genoclab_contact_name': 'Dr BOUDERBALA Hadjer',
        'genoclab_contact_role': 'Présidente du conseil d’administration de GENOCLAB (PCA)',
        'genoclab_contact_phone': '+213-554-050-460',
        'genoclab_contact_email': 'genoclab.essbo@gmail.com'},
 'en': {'genoclab_contact_name': 'Dr BOUDERBALA Hadjer',
        'genoclab_contact_role': 'Chair of the Board of Directors of GENOCLAB (PCA)',
        'genoclab_contact_phone': '+213-554-050-460',
        'genoclab_contact_email': 'genoclab.essbo@gmail.com'},
 'ar': {'genoclab_contact_name': 'Dr BOUDERBALA Hadjer',
        'genoclab_contact_role': 'رئيسة مجلس إدارة جينوصيلاب (PCA)',
        'genoclab_contact_phone': '+213-554-050-460',
        'genoclab_contact_email': 'genoclab.essbo@gmail.com'}}

def forwards(apps, schema_editor):
    Content = apps.get_model('core', 'PlatformContent')
    for lang, values in CONTACTS.items():
        for key, value in values.items():
            Content.objects.using(schema_editor.connection.alias).get_or_create(
                key=key, lang=lang, defaults={'value': value},
            )

class Migration(migrations.Migration):
    dependencies = [('core', '0034_arabic_ibtikar_labels')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
