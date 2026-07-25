from django.db import migrations


# Remplacements de marque : l'ESSBO est un établissement indépendant, sans
# lien avec l'« Université d'Oran ». On nettoie les contenus CMS déjà
# enregistrés en base (seed_content utilise get_or_create et n'écrase donc
# jamais les valeurs existantes — d'où cette migration de données).
REPLACEMENTS = {
    "جامعة وهران": "المدرسة العليا للعلوم البيولوجية بوهران",
    "Université d'Oran": "École Supérieure en Sciences Biologiques d'Oran (ESSBO)",
    "University of Oran": "Higher School of Biological Sciences of Oran (ESSBO)",
}


def scrub(apps, schema_editor):
    PlatformContent = apps.get_model('core', 'PlatformContent')
    for old, new in REPLACEMENTS.items():
        for pc in PlatformContent.objects.filter(value__contains=old):
            pc.value = pc.value.replace(old, new)
            pc.save(update_fields=['value'])


def noop(apps, schema_editor):
    # Irréversible : on ne restaure pas l'affiliation erronée.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_request_informed_members_and_more'),
    ]

    operations = [
        migrations.RunPython(scrub, noop),
    ]
