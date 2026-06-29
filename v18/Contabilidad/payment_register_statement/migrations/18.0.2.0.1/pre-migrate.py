# -*- coding: utf-8 -*-

def migrate(cr, version):
    """Emergency schema sync.

    If the module code is updated to include stored fields but the module wasn't
    upgraded yet, the ORM can try to read missing columns and crash (UndefinedColumn).

    This pre-migration makes sure the key columns exist before the ORM starts
    reading records during the upgrade.
    """
    cr.execute("""
        ALTER TABLE res_partner
            ADD COLUMN IF NOT EXISTS prs_expense_concept_id integer;
        ALTER TABLE account_payment
            ADD COLUMN IF NOT EXISTS prs_expense_concept_id integer;
        ALTER TABLE account_move
            ADD COLUMN IF NOT EXISTS prs_expense_concept_id integer;
        ALTER TABLE account_bank_statement_line
            ADD COLUMN IF NOT EXISTS prs_expense_concept_id integer;
    """)
