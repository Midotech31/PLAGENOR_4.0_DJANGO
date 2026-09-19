from django.db import migrations


COMPLETE_ACCOUNT = "Cpte CCP Agent comptable de l'ESSBO : 007999990000324044 14"


def update_defaults(apps, schema_editor):
    Content = apps.get_model('core', 'PlatformContent')
    Content.objects.filter(key='genoclab_quote_title', lang='fr', value='Facture Proforma').update(value='Devis')
    for key in ('genoclab_issuer_ccp', 'ohb_issuer_ccp'):
        Content.objects.filter(key=key, lang='fr', value__in=(
            "Cpte CCP Agent comptable de l'ESSBO : 007999990000",
            "Cpte CCP Agent comptable de l’ESSBO : 007999990000",
        )).update(value=COMPLETE_ACCOUNT)


class Migration(migrations.Migration):
    dependencies = [('core', '0041_ibtikarsubmission_ibtikarrevision_ibtikarattachment')]
    operations = [migrations.RunPython(update_defaults, migrations.RunPython.noop)]
