from django.db import migrations


def install(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':
        return
    schema_editor.execute("""
    CREATE FUNCTION erp_guard_import_batch() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Import history cannot be deleted'; END IF;
        IF OLD.status='APPLIED' THEN RAISE EXCEPTION 'Applied import history is immutable'; END IF;
        IF NEW.actor_id IS DISTINCT FROM OLD.actor_id OR NEW.kind IS DISTINCT FROM OLD.kind OR
           NEW.creation_key IS DISTINCT FROM OLD.creation_key OR NEW.creation_hash IS DISTINCT FROM OLD.creation_hash OR
           NEW.plan_id IS DISTINCT FROM OLD.plan_id OR NEW.filename IS DISTINCT FROM OLD.filename OR
           NEW.sha256 IS DISTINCT FROM OLD.sha256 OR NEW.payload IS DISTINCT FROM OLD.payload OR
           NEW.baselines IS DISTINCT FROM OLD.baselines OR NEW.reason IS DISTINCT FROM OLD.reason OR
           (NEW.report->'preview') IS DISTINCT FROM (OLD.report->'preview') THEN
            RAISE EXCEPTION 'The reviewed import content cannot be changed';
        END IF;
        RETURN NEW;
    END;
    $$;
    CREATE TRIGGER erp_import_batch_history BEFORE UPDATE OR DELETE ON erp_importbatch
        FOR EACH ROW EXECUTE FUNCTION erp_guard_import_batch();
    """)


def uninstall(apps,schema_editor):
    if schema_editor.connection.vendor=='postgresql':
        schema_editor.execute('DROP TRIGGER IF EXISTS erp_import_batch_history ON erp_importbatch; DROP FUNCTION IF EXISTS erp_guard_import_batch();')


class Migration(migrations.Migration):
    dependencies=[('erp','0014_importbatch')]
    operations=[migrations.RunPython(install,uninstall)]
