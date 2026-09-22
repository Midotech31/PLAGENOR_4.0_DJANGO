from django.db import migrations


IMMUTABLE=('erp_forecastobservation','erp_procurementrevision','erp_purchasereceiptlink')


def install(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':
        return
    quote=schema_editor.quote_name
    for table in IMMUTABLE:
        schema_editor.execute('CREATE TRIGGER '+quote(table+'_immutable')+' BEFORE UPDATE OR DELETE ON '+
            quote(table)+' FOR EACH ROW EXECUTE FUNCTION erp_reject_history_mutation()')
    schema_editor.execute("""
    CREATE FUNCTION erp_guard_procurement_lines() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE old_parent uuid; new_parent uuid;
    BEGIN
        IF TG_TABLE_NAME='erp_procurementline' THEN
            IF TG_OP<>'INSERT' THEN old_parent=OLD.plan_id; END IF;
            IF TG_OP<>'DELETE' THEN new_parent=NEW.plan_id; END IF;
            IF EXISTS(SELECT 1 FROM erp_procurementplan WHERE id IN (old_parent,new_parent)
                      AND approved_revision_id IS NOT NULL) THEN
                RAISE EXCEPTION 'Approved procurement lines are immutable';
            END IF;
        ELSE
            IF TG_OP<>'INSERT' THEN old_parent=OLD.order_id; END IF;
            IF TG_OP<>'DELETE' THEN new_parent=NEW.order_id; END IF;
            IF EXISTS(SELECT 1 FROM erp_purchaseorder WHERE id IN (old_parent,new_parent) AND status<>'DRAFT') THEN
                RAISE EXCEPTION 'Confirmed purchase order lines are immutable';
            END IF;
        END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END;
    $$;
    CREATE TRIGGER erp_plan_line_final BEFORE INSERT OR UPDATE OR DELETE ON erp_procurementline
        FOR EACH ROW EXECUTE FUNCTION erp_guard_procurement_lines();
    CREATE TRIGGER erp_order_line_final BEFORE INSERT OR UPDATE OR DELETE ON erp_purchaseorderline
        FOR EACH ROW EXECUTE FUNCTION erp_guard_procurement_lines();
    CREATE FUNCTION erp_guard_plan_approval() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.approved_revision_id IS NOT NULL AND
          (TG_OP='DELETE' OR NEW.approved_revision_id IS DISTINCT FROM OLD.approved_revision_id OR
           NEW.reference IS DISTINCT FROM OLD.reference OR NEW.year IS DISTINCT FROM OLD.year OR
           NEW.starts_on IS DISTINCT FROM OLD.starts_on OR NEW.ends_on IS DISTINCT FROM OLD.ends_on OR
           NEW.work_id IS DISTINCT FROM OLD.work_id) THEN
            RAISE EXCEPTION 'Approved procurement plan content is immutable';
        END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END;
    $$;
    CREATE TRIGGER erp_plan_final BEFORE UPDATE OR DELETE ON erp_procurementplan
        FOR EACH ROW EXECUTE FUNCTION erp_guard_plan_approval();
    CREATE OR REPLACE FUNCTION erp_guard_final_cdc() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE origin_id uuid; target_id uuid;
    BEGIN
        IF TG_TABLE_NAME='erp_cdcdossier' THEN
            IF TG_OP<>'INSERT' THEN origin_id=OLD.id; END IF;
            IF TG_OP<>'DELETE' THEN target_id=NEW.id; END IF;
        ELSIF TG_TABLE_NAME='erp_cdclot' THEN
            IF TG_OP<>'INSERT' THEN origin_id=OLD.dossier_id; END IF;
            IF TG_OP<>'DELETE' THEN target_id=NEW.dossier_id; END IF;
        ELSE
            IF TG_OP<>'INSERT' THEN SELECT dossier_id INTO origin_id FROM erp_cdclot WHERE id=OLD.lot_id; END IF;
            IF TG_OP<>'DELETE' THEN SELECT dossier_id INTO target_id FROM erp_cdclot WHERE id=NEW.lot_id; END IF;
        END IF;
        IF EXISTS(SELECT 1 FROM erp_cdcapproval WHERE dossier_id IN (origin_id,target_id)) THEN
            RAISE EXCEPTION 'Approved CDC content is immutable';
        END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END;
    $$;
    DROP TRIGGER erp_cdc_lot_final ON erp_cdclot;
    DROP TRIGGER erp_cdc_item_final ON erp_cdcitem;
    CREATE TRIGGER erp_cdc_lot_final BEFORE INSERT OR UPDATE OR DELETE ON erp_cdclot
        FOR EACH ROW EXECUTE FUNCTION erp_guard_final_cdc();
    CREATE TRIGGER erp_cdc_item_final BEFORE INSERT OR UPDATE OR DELETE ON erp_cdcitem
        FOR EACH ROW EXECUTE FUNCTION erp_guard_final_cdc();
    """)


def uninstall(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':
        return
    quote=schema_editor.quote_name
    schema_editor.execute("""
    DROP TRIGGER IF EXISTS erp_plan_line_final ON erp_procurementline;
    DROP TRIGGER IF EXISTS erp_order_line_final ON erp_purchaseorderline;
    DROP TRIGGER IF EXISTS erp_plan_final ON erp_procurementplan;
    DROP FUNCTION IF EXISTS erp_guard_procurement_lines();
    DROP FUNCTION IF EXISTS erp_guard_plan_approval();
    """)
    for table in IMMUTABLE:
        schema_editor.execute('DROP TRIGGER IF EXISTS '+quote(table+'_immutable')+' ON '+quote(table))


class Migration(migrations.Migration):
    dependencies=[('erp','0010_forecastobservation_procurementplan_procurementline_and_more')]
    operations=[migrations.RunPython(install,uninstall)]
