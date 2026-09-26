from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    quote = schema_editor.quote_name
    schema_editor.execute(
        'CREATE TRIGGER ' + quote('erp_equipmentinventorysource_immutable') +
        ' BEFORE UPDATE OR DELETE ON ' + quote('erp_equipmentinventorysource') +
        ' FOR EACH ROW EXECUTE FUNCTION erp_reject_history_mutation()'
    )
    schema_editor.execute("""
        CREATE OR REPLACE FUNCTION erp_guard_legacy_inventory_source()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Legacy inventory source records cannot be deleted';
            END IF;
            IF OLD.source_key IS DISTINCT FROM NEW.source_key
               OR OLD.source_file IS DISTINCT FROM NEW.source_file
               OR OLD.source_section IS DISTINCT FROM NEW.source_section
               OR OLD.source_row IS DISTINCT FROM NEW.source_row
               OR OLD.kind IS DISTINCT FROM NEW.kind
               OR OLD.fingerprint IS DISTINCT FROM NEW.fingerprint
               OR OLD.raw_data IS DISTINCT FROM NEW.raw_data THEN
                RAISE EXCEPTION 'Legacy inventory source evidence is immutable';
            END IF;
            RETURN NEW;
        END;
        $$;
    """)
    schema_editor.execute(
        'CREATE TRIGGER ' + quote('erp_legacyinventoryrecord_source_guard') +
        ' BEFORE UPDATE OR DELETE ON ' + quote('erp_legacyinventoryrecord') +
        ' FOR EACH ROW EXECUTE FUNCTION erp_guard_legacy_inventory_source()'
    )


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    quote = schema_editor.quote_name
    schema_editor.execute(
        'DROP TRIGGER IF EXISTS ' + quote('erp_legacyinventoryrecord_source_guard') +
        ' ON ' + quote('erp_legacyinventoryrecord')
    )
    schema_editor.execute(
        'DROP TRIGGER IF EXISTS ' + quote('erp_equipmentinventorysource_immutable') +
        ' ON ' + quote('erp_equipmentinventorysource')
    )
    schema_editor.execute('DROP FUNCTION IF EXISTS erp_guard_legacy_inventory_source()')


class Migration(migrations.Migration):
    dependencies = [('erp', '0027_equipment_inventory_source')]
    operations = [migrations.RunPython(install, uninstall)]
