from django.db import migrations


TABLES = (
    'erp_workcomment', 'erp_stockmovement', 'erp_stockentry', 'erp_stockreceipt',
    'erp_internalpreparation', 'erp_cdcrevision', 'erp_cdcgeneration', 'erp_cdcapproval',
    'erp_sampleevent', 'erp_temperaturereading', 'erp_storagetransfer',
    'erp_runrequirement', 'erp_runinput', 'erp_runoperation', 'erp_runallocation',
    'erp_runconsumption', 'erp_runbiologyevent',
)


def install(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    quote = schema_editor.quote_name
    for table in TABLES:
        schema_editor.execute('CREATE TRIGGER ' + quote(table + '_immutable') +
            ' BEFORE UPDATE OR DELETE ON ' + quote(table) +
            ' FOR EACH ROW EXECUTE FUNCTION erp_reject_history_mutation()')
    schema_editor.execute("""
        CREATE FUNCTION erp_guard_final_cdc() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE protected_dossier_id uuid;
        BEGIN
            IF TG_TABLE_NAME = 'erp_cdcdossier' THEN
                protected_dossier_id := OLD.id;
            ELSIF TG_TABLE_NAME = 'erp_cdclot' THEN
                protected_dossier_id := OLD.dossier_id;
            ELSE
                SELECT erp_cdclot.dossier_id INTO protected_dossier_id FROM erp_cdclot WHERE id = OLD.lot_id;
            END IF;
            IF EXISTS (SELECT 1 FROM erp_cdcapproval WHERE erp_cdcapproval.dossier_id = protected_dossier_id) THEN
                RAISE EXCEPTION 'An approved CDC dossier cannot be changed';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$;
        CREATE TRIGGER erp_cdc_dossier_final BEFORE UPDATE OR DELETE ON erp_cdcdossier
            FOR EACH ROW EXECUTE FUNCTION erp_guard_final_cdc();
        CREATE TRIGGER erp_cdc_lot_final BEFORE UPDATE OR DELETE ON erp_cdclot
            FOR EACH ROW EXECUTE FUNCTION erp_guard_final_cdc();
        CREATE TRIGGER erp_cdc_item_final BEFORE UPDATE OR DELETE ON erp_cdcitem
            FOR EACH ROW EXECUTE FUNCTION erp_guard_final_cdc();
    """)


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    quote = schema_editor.quote_name
    schema_editor.execute("""
        DROP TRIGGER IF EXISTS erp_cdc_item_final ON erp_cdcitem;
        DROP TRIGGER IF EXISTS erp_cdc_lot_final ON erp_cdclot;
        DROP TRIGGER IF EXISTS erp_cdc_dossier_final ON erp_cdcdossier;
        DROP FUNCTION IF EXISTS erp_guard_final_cdc();
    """)
    for table in reversed(TABLES):
        schema_editor.execute('DROP TRIGGER IF EXISTS ' + quote(table + '_immutable') + ' ON ' + quote(table))


class Migration(migrations.Migration):
    dependencies = [('erp', '0007_alter_sampleevent_kind_consumptionprofile_and_more')]
    operations = [migrations.RunPython(install, uninstall)]
