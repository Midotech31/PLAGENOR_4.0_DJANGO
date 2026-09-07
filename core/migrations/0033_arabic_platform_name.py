from django.db import migrations

CHANGES = [('fr',
  'hero_subtitle',
  'Plateforme Technologique de Génomique — ESSBO · ORAN',
  'Plateforme Technologique en Génomique — ESSBO · ORAN'),
 ('fr',
  'org_description',
  'PLAGENOR est la plateforme technologique de génomique de l’École Supérieure en Sciences Biologiques '
  'd’Oran (ESSBO). Elle accueille les demandes des étudiants algériens via IBTIKAR et les demandes de '
  'prestations scientifiques et techniques.',
  'PLAGENOR est la Plateforme Technologique en Génomique de l’École Supérieure en Sciences Biologiques '
  'd’Oran (ESSBO). Elle accueille les demandes des étudiants algériens via IBTIKAR et les demandes de '
  'prestations scientifiques et techniques.'),
 ('fr',
  'footer_description',
  'PLAGENOR — Plateforme technologique de génomique de l’ESSBO. Demandes d’analyses, suivi des '
  'prestations et remise des résultats.',
  'PLAGENOR — Plateforme Technologique en Génomique de l’ESSBO. Demandes d’analyses, suivi des '
  'prestations et remise des résultats.'),
 ('en',
  'org_description',
  'PLAGENOR is the genomics technology platform of the Higher School of Biological Sciences of Oran '
  '(ESSBO). It handles requests from Algerian students through IBTIKAR and requests for scientific and '
  'technical services.',
  'PLAGENOR is the Genomics Technology Platform of the Higher School of Biological Sciences of Oran '
  '(ESSBO). It handles requests from Algerian students through IBTIKAR and requests for scientific and '
  'technical services.'),
 ('ar',
  'hero_subtitle',
  'منصة التكنولوجيا الجينومية — المدرسة العليا في العلوم البيولوجية بوهران · وهران',
  'الأرضية التكنولوجية للجينوميك — المدرسة العليا في العلوم البيولوجية بوهران · وهران'),
 ('ar',
  'org_description',
  'PLAGENOR هي منصة تكنولوجيا الجينوم التابعة للمدرسة العليا للعلوم البيولوجية بوهران. تستقبل طلبات '
  'الطلبة الجزائريين عبر منصة إبتكار وطلبات الخدمات العلمية والتقنية.',
  'PLAGENOR هي الأرضية التكنولوجية للجينوميك التابعة للمدرسة العليا للعلوم البيولوجية بوهران. تستقبل '
  'طلبات الطلبة الجزائريين عبر منصة إبتكار وطلبات الخدمات العلمية والتقنية.'),
 ('ar',
  'footer_description',
  'PLAGENOR — منصة تكنولوجيا الجينوم التابعة لـ ESSBO. طلبات التحليل ومتابعة الخدمات وتسليم النتائج.',
  'PLAGENOR — الأرضية التكنولوجية للجينوميك التابعة لـ ESSBO. طلبات التحليل ومتابعة الخدمات وتسليم '
  'النتائج.')]

def forwards(apps, schema_editor):
    Content = apps.get_model('core', 'PlatformContent')
    for lang, key, old, new in CHANGES:
        Content.objects.using(schema_editor.connection.alias).filter(
            key=key, lang=lang, value=old,
        ).update(value=new)

class Migration(migrations.Migration):
    dependencies = [('core', '0032_arabic_institution_names')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
