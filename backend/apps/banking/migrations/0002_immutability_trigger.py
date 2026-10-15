"""Once a deposit leaves PENDING_SETTLEMENT its figures are frozen at the database level."""
from django.db import migrations

SQL = """
CREATE OR REPLACE FUNCTION cmrs_protect_deposit() RETURNS trigger AS $$
BEGIN
    IF NEW.amount <> OLD.amount OR NEW.reference_number <> OLD.reference_number
       OR NEW.bank_name <> OLD.bank_name OR NEW.reconciled_amount <> OLD.reconciled_amount
       OR NEW.branch_id <> OLD.branch_id OR NEW.deposit_date <> OLD.deposit_date THEN
        RAISE EXCEPTION 'Deposit % figures are immutable', OLD.deposit_number
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF OLD.status <> 'PENDING_SETTLEMENT' AND (
        NEW.status <> OLD.status OR NEW.settled_amount IS DISTINCT FROM OLD.settled_amount
        OR NEW.settlement_date IS DISTINCT FROM OLD.settlement_date) THEN
        RAISE EXCEPTION 'Deposit % is already %; it cannot be modified', OLD.deposit_number, OLD.status
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER banking_deposit_immutable
    BEFORE UPDATE ON banking_bankdeposit
    FOR EACH ROW EXECUTE FUNCTION cmrs_protect_deposit();

CREATE TRIGGER banking_deposit_no_delete
    BEFORE DELETE ON banking_bankdeposit
    FOR EACH ROW EXECUTE FUNCTION cmrs_block_delete();

CREATE TRIGGER core_auditlog_append_only
    BEFORE UPDATE OR DELETE ON core_auditlog
    FOR EACH ROW EXECUTE FUNCTION cmrs_block_delete();
"""

REVERSE = """
DROP TRIGGER IF EXISTS core_auditlog_append_only ON core_auditlog;
DROP TRIGGER IF EXISTS banking_deposit_no_delete ON banking_bankdeposit;
DROP TRIGGER IF EXISTS banking_deposit_immutable ON banking_bankdeposit;
DROP FUNCTION IF EXISTS cmrs_protect_deposit();
"""


def _postgres_only(sql):
    """The triggers are PostgreSQL-specific; a local SQLite quick-start skips them."""
    def run(apps, schema_editor):
        if schema_editor.connection.vendor == "postgresql":
            with schema_editor.connection.cursor() as cursor:
                cursor.execute(sql)
    return run


class Migration(migrations.Migration):
    dependencies = [("banking", "0001_initial"), ("cash", "0002_immutability_trigger")]
    operations = [migrations.RunPython(_postgres_only(SQL), _postgres_only(REVERSE))]
