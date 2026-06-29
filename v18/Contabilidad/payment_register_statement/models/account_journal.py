# -*- coding: utf-8 -*-

from odoo import models, fields, _


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    # ── Extractos automáticos ────────────────────────────────────────────────

    auto_extract_enabled = fields.Boolean(
        string="Crear extractos automáticos",
        help=(
            "Si está activo, los pagos que involucren este diario crearán "
            "automáticamente una línea de extracto bancario."
        ),
    )

    prs_auto_statement_balance = fields.Boolean(
        string="Calcular aut. saldo estados de cuenta",
        help=(
            "Si está activo, los estados de cuenta de este diario calculan "
            "automáticamente el saldo inicial y final en base al estado anterior "
            "y a sus extractos."
        ),
    )

    prs_only_reconciled_statements = fields.Boolean(
        string="Solo contabilizar conciliados",
        help=(
            "Si está activo, el cálculo de los estados de cuenta y del Balance de caja "
            "solo tendrá en cuenta las líneas de extracto conciliadas."
        ),
        default=False,
    )

    prs_split_checks_per_statement = fields.Boolean(
        string="Extracto por cheque individual",
        default=False,
        help=(
            "Si está activo, cuando un pago tiene múltiples cheques (l10n_latam) "
            "se crea una línea de extracto bancario separada por cada cheque, "
            "usando el número del cheque como referencia. "
            "Si está desactivado (por defecto), se crea un único extracto por el total del pago."
        ),
    )

    prs_warn_missing_memo = fields.Boolean(
        string="Avisar si falta Memo",
        default=True,
        help=(
            "Si está activo, se envía una notificación de advertencia al validar un pago "
            "que no tiene el campo 'Memo' completado. "
            "Desactivar en diarios donde el memo no es relevante (ej. POS)."
        ),
    )

    prs_allow_delete_statement_with_payments = fields.Boolean(
        string="Permitir borrar estados con pagos",
        default=False,
        help=(
            "Si está activo, permite eliminar Estados de Cuenta aunque tengan "
            "líneas vinculadas a pagos. El pago NO se borra — solo se elimina "
            "el estado de cuenta. Útil para corregir estados creados en el "
            "diario equivocado.\n\n"
            "Si está desactivado (default), el sistema obliga a borrar el "
            "estado desde el pago asociado para mantener la consistencia contable."
        ),
    )

    # ── Multiempresa (solo diarios de efectivo) ──────────────────────────────

    allowed_company_ids = fields.Many2many(
        'res.company',
        'account_journal_allowed_company_rel',
        'journal_id',
        'company_id',
        string='Empresas permitidas',
        help=(
            'Permite que este diario de EFECTIVO sea visible y utilizable en varias empresas. '
            'Este comportamiento se aplica solo a diarios de tipo efectivo en este módulo.'
        ),
    )

    # ── Métodos ──────────────────────────────────────────────────────────────

    def write(self, vals):
        """Si se cambia el flag de cálculo automático, recalcular estados ABIERTOS."""
        recalc = any(k in vals for k in ('prs_auto_statement_balance', 'prs_only_reconciled_statements'))
        res = super().write(vals)
        if recalc:
            try:
                for journal in self:
                    if journal.type not in ('cash', 'bank'):
                        continue
                    sts = self.env['account.bank.statement'].search(
                        [('journal_id', '=', journal.id)], order='date asc, id asc'
                    )
                    open_sts = sts.filtered(lambda s: getattr(s, 'prs_state', 'open') == 'open')
                    if open_sts:
                        if getattr(journal, 'prs_auto_statement_balance', False):
                            # Flag activado: encadenar saldos con lógica PRS
                            open_sts._prs_recompute_balances()
                        else:
                            # Flag desactivado: al menos sincronizar balance_end
                            # para evitar el aviso naranja y el color rojo.
                            # Odoo va a recomputar balance_end pero puede usar cache
                            # stale — lo corregimos con SQL directo.
                            for st in open_sts:
                                self.env.cr.execute(
                                    "SELECT balance_start FROM account_bank_statement WHERE id = %s",
                                    (st.id,)
                                )
                                row = self.env.cr.fetchone()
                                db_start = row[0] if row else (st.balance_start or 0.0)
                                total = sum(st.line_ids.mapped('amount'))
                                correct_end = db_start + total
                                self.env.cr.execute(
                                    "UPDATE account_bank_statement SET balance_end = %s WHERE id = %s",
                                    (correct_end, st.id)
                                )
                            open_sts.invalidate_recordset(['balance_end'])
            except Exception:
                pass
        return res

    def prs_get_reconciliation_sidebar_data(self):
        """Devuelve los importes que muestra el panel izquierdo de conciliación."""
        self.ensure_one()

        if self.type not in ('cash', 'bank'):
            return False

        Statement = self.env['account.bank.statement']

        statement = Statement.search([
            ('journal_id', '=', self.id),
            ('prs_state', '=', 'open'),
        ], order='date desc, id desc', limit=1)

        if not statement:
            statement = Statement.search(
                [('journal_id', '=', self.id)], order='date desc, id desc', limit=1
            )

        currency = self.currency_id or self.company_id.currency_id

        if not statement:
            return {
                'journal_id': self.id,
                'statement_id': False,
                'statement_date': False,
                'statement_name': False,
                'general_balance': 0.0,
                'statement_balance': 0.0,
                'currency_symbol': currency.symbol if currency else '$',
                'only_reconciled': bool(self.prs_only_reconciled_statements),
                'auto_statement_balance': bool(self.prs_auto_statement_balance),
            }

        try:
            if getattr(self, 'prs_auto_statement_balance', False) and getattr(statement, 'prs_state', 'open') == 'open':
                statement._prs_recompute_balances(start_from=statement)
                statement.invalidate_recordset()
        except Exception:
            pass

        end_value = 0.0
        if 'balance_end_real' in statement._fields and statement.balance_end_real is not False:
            end_value = float(statement.balance_end_real or 0.0)
        elif 'balance_end' in statement._fields and statement.balance_end is not False:
            end_value = float(statement.balance_end or 0.0)

        start_value = float(statement.balance_start or 0.0)

        try:
            statement_balance = float(statement._prs_get_lines_total())
        except Exception:
            statement_balance = end_value - start_value

        return {
            'journal_id': self.id,
            'statement_id': statement.id,
            'statement_date': str(statement.date or ''),
            'statement_name': statement.display_name,
            'general_balance': end_value,
            'statement_balance': statement_balance,
            'currency_symbol': currency.symbol if currency else '$',
            'only_reconciled': bool(self.prs_only_reconciled_statements),
            'auto_statement_balance': bool(self.prs_auto_statement_balance),
        }

    def open_transfer_money(self):
        """Reemplaza el botón Transferencias internas del tablero bancario con el wizard PRS."""
        self.ensure_one()
        if self.type not in ('cash', 'bank'):
            return super().open_transfer_money()
        action = self.env.ref(
            'payment_register_statement.action_prs_internal_transfer_wizard'
        ).read()[0]
        ctx = dict(self.env.context or {})
        ctx.update({
            'default_source_journal_id': self.id,
            'allowed_company_ids': [self.company_id.id],
        })
        action['context'] = ctx
        action['name'] = _('Transferencia interna')
        return action
