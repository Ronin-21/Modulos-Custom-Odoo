# -*- coding: utf-8 -*-

"""Bootstrapping de esquema para evitar caídas por columnas faltantes.

En Odoo.sh es común que al subir código nuevo (campos almacenados) el servidor
reinicie y cargue el registro *antes* de que se ejecute un Upgrade del módulo.
Si el core hace prefetch de `res.partner` (ej: al resolver idioma en
`get_lang()`), cualquier campo nuevo con columna aún no creada provoca un 500
que impide entrar a la UI para actualizar.

Este hook asegura, UNA vez por worker y base de datos, que existan las columnas
críticas usadas por este módulo. Luego podrás hacer Upgrade normal del módulo
para que Odoo cree constraints/índices según corresponda.
"""

import logging

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def _pre_dispatch(self, rule, args):
        # Ejecutar best-effort y solo una vez por registry (por DB y worker)
        try:
            reg = request.env.registry
            if not getattr(reg, '_prs_schema_bootstrapped', False):
                self._prs_ensure_schema(request.env.cr)
                # DDL es transaccional en PostgreSQL; commiteamos para que no se
                # revierta si luego falla la request.
                request.env.cr.commit()
                setattr(reg, '_prs_schema_bootstrapped', True)
        except Exception:
            # No romper el request por el fix; solo log.
            _logger.exception('PRS: fallo al asegurar esquema (bootstrapping).')
        return super()._pre_dispatch(rule, args)

    @staticmethod
    def _prs_ensure_schema(cr):
        """Crea columnas faltantes en tablas core usadas por el módulo."""

        # helper
        def add_col(table, col, sql_type):
            cr.execute(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {sql_type}')

        # res.partner (causa del 500 en login por prefetch)
        add_col('res_partner', 'prs_expense_concept_id', 'int4')

        # account.move / account.payment / statement lines
        add_col('account_move', 'prs_expense_concept_id', 'int4')

        add_col('account_payment', 'prs_expense_concept_id', 'int4')
        add_col('account_payment', 'prs_statement_id', 'int4')
        add_col('account_payment', 'prs_is_misc_expense', 'boolean')

        add_col('account_bank_statement', 'prs_state', 'varchar')
        add_col('account_bank_statement', 'prs_balance_start_manual', 'boolean')

        add_col('account_journal', 'auto_extract_enabled', 'boolean')
        add_col('account_journal', 'prs_auto_statement_balance', 'boolean')
        add_col('account_journal', 'prs_smart_reconcile_models', 'boolean')
        add_col('account_journal', 'prs_smart_reconcile_auto', 'boolean')

        add_col('account_bank_statement_line', 'payment_id', 'int4')
        add_col('account_bank_statement_line', 'prs_expense_concept_id', 'int4')
        add_col('account_bank_statement_line', 'prs_smart_suggested_aml_id', 'int4')
        add_col('account_bank_statement_line', 'prs_smart_suggested_move_id', 'int4')
        add_col('account_bank_statement_line', 'prs_smart_suggested_note', 'varchar')
        add_col('account_bank_statement_line', 'prs_smart_last_run', 'timestamp')

        # account.reconcile.model (gastos varios)
        add_col('account_reconcile_model', 'prs_use_for_misc_expense', 'boolean')
        add_col('account_reconcile_model', 'prs_misc_expense_account_id', 'int4')
        add_col('account_reconcile_model', 'prs_misc_payment_type', 'varchar')
        add_col('account_reconcile_model', 'prs_misc_memo_contains', 'varchar')
