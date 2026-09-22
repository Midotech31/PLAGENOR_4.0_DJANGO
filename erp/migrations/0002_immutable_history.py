from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute("""
        CREATE FUNCTION erp_reject_history_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'ERP historical records are immutable';
        END;
        $$;
        CREATE TRIGGER erp_audit_immutable BEFORE UPDATE OR DELETE ON erp_auditevent
            FOR EACH ROW EXECUTE FUNCTION erp_reject_history_mutation();
        CREATE TRIGGER erp_price_immutable BEFORE UPDATE OR DELETE ON erp_priceobservation
            FOR EACH ROW EXECUTE FUNCTION erp_reject_history_mutation();
    """)


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute("""
        DROP TRIGGER IF EXISTS erp_audit_immutable ON erp_auditevent;
        DROP TRIGGER IF EXISTS erp_price_immutable ON erp_priceobservation;
        DROP FUNCTION IF EXISTS erp_reject_history_mutation();
    """)


class Migration(migrations.Migration):
    dependencies = [('erp', '0001_reference_catalogue_and_storage')]
    operations = [migrations.RunPython(install, uninstall)]
