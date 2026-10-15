"""
Defence in depth: PostgreSQL refuses to change the money or the parties on a receipt
once it exists, no matter which code path (ORM, queryset.update(), raw SQL, admin)
attempts it. Corrections are made by voiding and re-issuing, never by editing.
"""
from django.db import migrations

SQL = """
CREATE OR REPLACE FUNCTION cmrs_protect_collection() RETURNS trigger AS $$
BEGIN
    IF NEW.amount <> OLD.amount OR NEW.loan_id <> OLD.loan_id OR NEW.agent_id <> OLD.agent_id
       OR NEW.customer_id <> OLD.customer_id OR NEW.branch_id <> OLD.branch_id
       OR NEW.receipt_number <> OLD.receipt_number OR NEW.collected_at <> OLD.collected_at THEN
        RAISE EXCEPTION 'Receipt % is immutable: amount, parties and number cannot change', OLD.receipt_number
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF OLD.status = 'VOIDED' AND NEW.status <> 'VOIDED' THEN
        RAISE EXCEPTION 'Voided receipt % cannot be reinstated', OLD.receipt_number
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER cash_collection_immutable
    BEFORE UPDATE ON cash_collection
    FOR EACH ROW EXECUTE FUNCTION cmrs_protect_collection();

CREATE OR REPLACE FUNCTION cmrs_block_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Rows of % cannot be deleted', TG_TABLE_NAME
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER cash_collection_no_delete
    BEFORE DELETE ON cash_collection
    FOR EACH ROW EXECUTE FUNCTION cmrs_block_delete();
"""

REVERSE = """
DROP TRIGGER IF EXISTS cash_collection_no_delete ON cash_collection;
DROP TRIGGER IF EXISTS cash_collection_immutable ON cash_collection;
DROP FUNCTION IF EXISTS cmrs_protect_collection();
"""


class Migration(migrations.Migration):
    dependencies = [("cash", "0001_initial"), ("core", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
