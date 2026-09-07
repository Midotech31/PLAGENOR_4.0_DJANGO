from django.db import migrations

COPY = {'fr': 'Canal ouvert à tous les étudiants algériens, quel que soit leur établissement. Soumettez vos demandes d’analyses dans le cadre de vos projets de recherche, avec une prise en charge soumise à la validation du dossier et du financement IBTIKAR.', 'en': 'Open to all Algerian students, regardless of their institution. Submit analysis requests for your research projects, with funding subject to approval of your application and IBTIKAR financing.', 'ar': 'قناة مفتوحة لجميع الطلبة الجزائريين، مهما كانت مؤسساتهم. أرسلوا طلبات التحليل في إطار مشاريعكم البحثية، مع تكفّل يخضع للموافقة على الملف وتمويل ابتكار.'}


def update_copy(apps, schema_editor):
    Content = apps.get_model('core', 'PlatformContent')
    for language, value in COPY.items():
        Content.objects.using(schema_editor.connection.alias).update_or_create(
            key='ibtikar_description', lang=language, defaults={'value': value})


class Migration(migrations.Migration):
    dependencies = [('core', '0032_precise_vat_rate')]
    operations = [migrations.RunPython(update_copy, migrations.RunPython.noop)]
