# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Ensure DB columns exist for newly introduced stored fields.

    This prevents runtime crashes like:
    psycopg2.errors.UndefinedColumn: column res_partner.prs_expense_concept_id does not exist

    The ORM will still handle full schema/metadata during module upgrade.
    """
    cr.execute("""
        ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS prs_expense_concept_id integer;
        ALTER TABLE account_payment ADD COLUMN IF NOT EXISTS prs_expense_concept_id integer;
        ALTER TABLE account_move ADD COLUMN IF NOT EXISTS prs_expense_concept_id integer;
        ALTER TABLE account_bank_statement_line ADD COLUMN IF NOT EXISTS prs_expense_concept_id integer;
    """)

    # Optional indexes (safe / idempotent)
    cr.execute("""
        CREATE INDEX IF NOT EXISTS res_partner_prs_expense_concept_id_idx ON res_partner (prs_expense_concept_id);
        CREATE INDEX IF NOT EXISTS account_payment_prs_expense_concept_id_idx ON account_payment (prs_expense_concept_id);
        CREATE INDEX IF NOT EXISTS account_move_prs_expense_concept_id_idx ON account_move (prs_expense_concept_id);
        CREATE INDEX IF NOT EXISTS account_bank_statement_line_prs_expense_concept_id_idx ON account_bank_statement_line (prs_expense_concept_id);
    """)
