from django.db import migrations

ADDRESSES = {'fr': 'BP 1042 SAIM MOHAMED, Cité Emir Abdelkader (EX-INESSMO) 31000 Oran', 'en': 'BP 1042 SAIM MOHAMED, Cité Emir Abdelkader (EX-INESSMO) 31000 Oran', 'ar': 'ص.ب. 1042 صايم محمد، حي الأمير عبد القادر (EX-INESSMO)، 31000 وهران'}

def forwards(apps, schema_editor):
    Content = apps.get_model('core', 'PlatformContent')
    for lang, value in ADDRESSES.items():
        for key in ('contact_address', 'about_contact_address'):
            Content.objects.using(schema_editor.connection.alias).update_or_create(
                key=key, lang=lang, defaults={'value': value},
            )

class Migration(migrations.Migration):
    dependencies = [('core', '0035_genoclab_public_contact')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
