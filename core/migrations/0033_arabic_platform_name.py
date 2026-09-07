from django.db import migrations

CHANGES = [('hero_subtitle',
  'منصة التكنولوجيا الجينومية — المدرسة العليا في العلوم البيولوجية بوهران · وهران',
  'الأرضية التكنولوجية للجينوميك — المدرسة العليا في العلوم البيولوجية بوهران · وهران'),
 ('org_description',
  'PLAGENOR هي منصة تكنولوجيا الجينوم التابعة للمدرسة العليا للعلوم البيولوجية بوهران. تستقبل '
  'طلبات الطلبة الجزائريين عبر منصة إبتكار وطلبات الخدمات العلمية والتقنية.',
  'PLAGENOR هي الأرضية التكنولوجية للجينوميك التابعة للمدرسة العليا للعلوم البيولوجية بوهران. '
  'تستقبل طلبات الطلبة الجزائريين عبر منصة إبتكار وطلبات الخدمات العلمية والتقنية.'),
 ('footer_description',
  'PLAGENOR — منصة تكنولوجيا الجينوم التابعة لـ ESSBO. طلبات التحليل ومتابعة الخدمات وتسليم '
  'النتائج.',
  'PLAGENOR — الأرضية التكنولوجية للجينوميك التابعة لـ ESSBO. طلبات التحليل ومتابعة الخدمات وتسليم '
  'النتائج.')]

def forwards(apps, schema_editor):
    Content = apps.get_model('core', 'PlatformContent')
    for key, old, new in CHANGES:
        Content.objects.using(schema_editor.connection.alias).filter(
            key=key, lang='ar', value=old,
        ).update(value=new)

class Migration(migrations.Migration):
    dependencies = [('core', '0032_arabic_institution_names')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
