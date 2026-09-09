from django.db import migrations

VALUES = {'footer_brand': 'الأرضية التكنولوجية للجينوميك', 'footer_description': 'الأرضية التكنولوجية للجينوميك التابعة للمدرسة العليا في العلوم البيولوجية بوهران. طلبات التحليل ومتابعة الخدمات وتسليم النتائج.', 'footer_credit': 'الأرضية التكنولوجية للجينوميك — تصميم البروفيسور محمد مرزوق | المدرسة العليا في العلوم البيولوجية بوهران'}

def forwards(apps, schema_editor):
    Content = apps.get_model('core', 'PlatformContent')
    for key, value in VALUES.items():
        Content.objects.using(schema_editor.connection.alias).update_or_create(
            key=key, lang='ar', defaults={'value': value},
        )

class Migration(migrations.Migration):
    dependencies = [('core', '0037_arabic_genoclab_contact_name')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
