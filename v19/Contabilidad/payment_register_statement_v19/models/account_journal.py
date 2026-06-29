# -*- coding: utf-8 -*-

from odoo import api, models, fields, _


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

    prs_auto_reconcile = fields.Boolean(
        string="Conciliar extracto automáticamente",
        default=False,
        help=(
            "Si está activo, la línea de extracto creada automáticamente a partir de "
            "un pago se concilia (cierra) de inmediato contra el apunte de recibos/pagos "
            "pendientes de ese pago.\n\n"
            "Usar SOLO en diarios donde el pago de Odoo es el registro definitivo del "
            "dinero (efectivo, transferencias cargadas a mano). NO usar en diarios que "
            "importan el extracto bancario, para evitar doble conteo.\n\n"
            "Los movimientos sin pago vinculado exacto (extractos manuales, gastos, "
            "parciales) siguen quedando disponibles para conciliar a mano."
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


    # ── Posición fiscal automática ───────────────────────────────────────────
    # Cuando está configurada, cualquier factura creada con este diario recibe
    # automáticamente esta posición fiscal (sin importar el módulo que la cree).
    # Útil para diarios no-fiscales o específicos de ciertos clientes.

    prs_fiscal_position_id = fields.Many2one(
        comodel_name='account.fiscal.position',
        string='Posición fiscal automática',
        check_company=True,
        ondelete='set null',
        help=(
            'Si está configurada, las facturas creadas con este diario reciben '
            'automáticamente esta posición fiscal, independientemente del módulo '
            'o flujo que las genere. Tiene prioridad sobre la posición del cliente.\n\n'
            'Caso de uso típico: diarios no-fiscales (sin ARCA) que aplican una '
            '"Posición fiscal — Venta no fiscal" para eliminar el IVA del comprobante.'
        ),
    )

    # ── Activación global PRS por diario ────────────────────────────────────
    # Non-stored: backed by ir.config_parameter to avoid SQL column issues on upgrade.

    prs_payment_register_enabled = fields.Boolean(
        string="Activar Payment Register",
        compute="_compute_prs_journal_settings",
        inverse="_inverse_prs_journal_settings",
        search="_search_prs_payment_register_enabled",
        readonly=False,
        help="Activa las opciones PRS de extractos, pagos, depositos y flujo para este diario.",
    )

    def _prs_journal_param_key(self, field_name):
        self.ensure_one()
        return 'payment_register_statement_v19.account_journal.%s.%s' % (field_name, self.id)

    @api.model
    def _prs_bool_from_param(self, value):
        return str(value or '').lower() in ('1', 'true', 'yes', 'on')

    def _compute_prs_journal_settings(self):
        ICP = self.env['ir.config_parameter'].sudo()
        for journal in self:
            journal.prs_payment_register_enabled = self._prs_bool_from_param(
                ICP.get_param(journal._prs_journal_param_key('prs_payment_register_enabled'))
            )

    def _inverse_prs_journal_settings(self):
        ICP = self.env['ir.config_parameter'].sudo()
        for journal in self:
            ICP.set_param(journal._prs_journal_param_key('prs_payment_register_enabled'), '1' if journal.prs_payment_register_enabled else '0')

    def _search_prs_journal_bool_param(self, field_name, operator, value):
        if operator not in ('=', '!='):
            return [('id', '=', 0)]
        # Una sola query a ir.config_parameter en lugar de N (una por diario).
        key_prefix = 'payment_register_statement_v19.account_journal.%s.' % field_name
        ICP = self.env['ir.config_parameter'].sudo()
        params = ICP.search([('key', 'like', key_prefix)])
        enabled_ids = []
        for param in params:
            if str(param.value or '').lower() in ('1', 'true', 'yes', 'on'):
                try:
                    enabled_ids.append(int(param.key[len(key_prefix):]))
                except (ValueError, TypeError):
                    pass
        want_true = bool(value)
        if (operator == '=' and want_true) or (operator == '!=' and not want_true):
            return [('id', 'in', enabled_ids)]
        return [('id', 'not in', enabled_ids)]

    def _search_prs_payment_register_enabled(self, operator, value):
        return self._search_prs_journal_bool_param('prs_payment_register_enabled', operator, value)

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
            'payment_register_statement_v19.action_prs_internal_transfer_wizard'
        ).read()[0]
        ctx = dict(self.env.context or {})
        ctx.update({
            'default_source_journal_id': self.id,
            'allowed_company_ids': [self.company_id.id],
        })
        action['context'] = ctx
        action['name'] = _('Transferencia interna')
        return action
