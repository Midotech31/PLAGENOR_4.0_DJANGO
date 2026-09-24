from django.db import migrations


TABLES=('erp_resourcedocument','erp_alertacknowledgement','erp_alertdigest')


def install(apps,schema_editor):
    if schema_editor.connection.vendor=='postgresql':
        quote=schema_editor.quote_name
        for table in TABLES:
            schema_editor.execute('CREATE TRIGGER '+quote(table+'_immutable')+' BEFORE UPDATE OR DELETE ON '+quote(table)+
                ' FOR EACH ROW EXECUTE FUNCTION erp_reject_history_mutation()')


def uninstall(apps,schema_editor):
    if schema_editor.connection.vendor=='postgresql':
        quote=schema_editor.quote_name
        for table in TABLES:
            schema_editor.execute('DROP TRIGGER IF EXISTS '+quote(table+'_immutable')+' ON '+quote(table))


class Migration(migrations.Migration):
    dependencies=[('erp','0017_chemicalprofile_hazardtag_resourcedocument_and_more')]
    operations=[migrations.RunPython(install,uninstall)]
