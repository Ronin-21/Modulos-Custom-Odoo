# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class CashierCloseWizardLine(models.TransientModel):
    _name = 'sale.cashier.close.wizard.line'
    _description = 'Línea de Cierre de Caja (Wizard)'

    wizard_id = fields.Many2one('sale.cashier.close.wizard', ondelete='cascade')
    # No required=True: Odoo puede generar una línea vacía temporal si el usuario
    # toca "Agregar una línea". La acción de cierre filtra esas líneas.
    payment_journal_id = fields.Many2one('account.journal', string='Medio de pago', readonly=True)
    amount_expected = fields.Monetary(string='Esperado', readonly=True, currency_field='currency_id')
    amount_expected_original = fields.Monetary(
        string='Esperado original', readonly=True, currency_field='currency_id',
        help='Importe bruto esperado antes de descontar el fondo retenido. Referencia interna.',
    )
    amount_real = fields.Monetary(string='Real (ingresado)', default=0.0, currency_field='currency_id')
    difference = fields.Monetary(string='Diferencia', compute='_compute_difference', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id', readonly=True)
    notes = fields.Char(string='Observaciones')

    @api.depends('amount_real', 'amount_expected')
    def _compute_difference(self):
        for line in self:
            line.difference = line.amount_real - line.amount_expected


class SaleCashierCloseWizard(models.TransientModel):
    _name = 'sale.cashier.close.wizard'
    _description = 'Wizard de Cierre de Sesión de Caja'

    session_id = fields.Many2one('sale.cashier.session', string='Sesión', required=True, readonly=True)
    cashier_id = fields.Many2one(related='session_id.cashier_id', string='Cajero', readonly=True)
    date = fields.Date(related='session_id.date', string='Fecha', readonly=True)
    total_orders = fields.Integer(related='session_id.total_orders', string='Pedidos cobrados', readonly=True)
    currency_id = fields.Many2one(related='session_id.currency_id', readonly=True)
    total_collected = fields.Monetary(
        related='session_id.total_collected', string='Cobros registrados', readonly=True, currency_field='currency_id',
    )
    opening_balance = fields.Monetary(
        related='session_id.opening_balance', string='Fondo inicial', readonly=True, currency_field='currency_id',
    )
    # Removido: print_on_close — la impresión ahora se hace desde el modal de confirmación de cierre.
    line_ids = fields.One2many('sale.cashier.close.wizard.line', 'wizard_id', string='Detalle por medio de pago')
    carry_over_amount = fields.Monetary(
        string='Fondo para próxima sesión',
        default=0.0,
        currency_field='currency_id',
        help='Efectivo que queda en el cajón para el próximo turno. '
             'Se descuenta del esperado de rendición en efectivo.',
    )
    total_expected = fields.Monetary(
        string='Esperado de rendición',
        compute='_compute_totals',
        currency_field='currency_id',
        help='Suma esperada a rendir: cobros registrados por medio de pago + fondo inicial en efectivo.',
    )
    total_real = fields.Monetary(
        string='Contado por cajero', compute='_compute_totals', currency_field='currency_id',
    )
    total_difference = fields.Monetary(
        string='Diferencia total', compute='_compute_totals', currency_field='currency_id',
    )
    total_deposit = fields.Monetary(
        string='A depositar',
        compute='_compute_totals',
        currency_field='currency_id',
        help='Efectivo contado menos el fondo retenido para la próxima sesión.',
    )
    notes = fields.Text(string='Observaciones del cierre')

    @api.depends('line_ids.amount_real', 'line_ids.amount_expected', 'line_ids.payment_journal_id', 'carry_over_amount')
    def _compute_totals(self):
        for wiz in self:
            valid_lines = wiz.line_ids.filtered(lambda l: l.payment_journal_id)
            wiz.total_expected = sum(valid_lines.mapped('amount_expected'))
            wiz.total_real = sum(valid_lines.mapped('amount_real'))
            wiz.total_difference = wiz.total_real - wiz.total_expected
            wiz.total_deposit = wiz.total_real - (wiz.carry_over_amount or 0.0)

    @api.onchange('carry_over_amount')
    def _onchange_carry_over_amount(self):
        """Valida que el fondo retenido no supere el efectivo físicamente contado.

        No modifica las líneas: 'Contado' siempre refleja lo que el cajero
        tiene en el cajón. El carry-over solo determina cuánto de ese conteo
        queda en el cajón vs. cuánto se deposita (total_deposit).
        La diferencia (faltante/sobrante) se calcula como contado − esperado,
        independientemente del carry-over.
        """
        carry = self.carry_over_amount or 0.0
        if carry < 0:
            self.carry_over_amount = 0.0
            return
        cash_real = sum(
            l.amount_real for l in self.line_ids
            if l.payment_journal_id and l.payment_journal_id.type == 'cash'
        )
        if carry > cash_real + 0.009:
            return {'warning': {
                'title': _('Fondo retenido excesivo'),
                'message': _(
                    'El fondo retenido ($%.2f) supera el efectivo contado ($%.2f).\n'
                    'Solo podés retener hasta lo que tenés físicamente en el cajón.'
                ) % (carry, cash_real),
            }}

    def _add_amount(self, totals, journal, amount):
        if not journal or not journal.id:
            return
        if journal.id not in totals:
            totals[journal.id] = {'journal': journal, 'amount': 0.0}
        totals[journal.id]['amount'] += amount or 0.0

    def _valid_payment_states(self):
        # Odoo usa 'posted'. Dejamos variantes defensivas para bases migradas/custom.
        return ['posted', 'in_process', 'paid']

    def _get_session_payment_totals(self, session):
        """Importes esperados por diario de cobro.

        La fuente principal es account.payment vinculado a la sesión. No se toma
        la factura/reconciliación como fuente principal porque puede mezclar
        pagos de otras sesiones. Este criterio replica el cierre POS: se rinde
        lo efectivamente cobrado en la sesión, agrupado por medio de pago.
        """
        totals = {}
        Payment = self.env['account.payment'].sudo()

        domain = [
            ('op_cashier_session_id', '=', session.id),
            ('payment_type', '=', 'inbound'),
            ('state', 'not in', ['draft', 'cancel', 'cancelled', 'canceled']),
        ]
        payments = Payment.search(domain)

        # Fallback para pagos creados por versiones viejas del módulo.
        if not payments and session.order_ids:
            paid_orders = session.order_ids.filtered(
                lambda o: o.operational_state in ('paid', 'dispatched')
            )
            payments = Payment.search([
                ('op_sale_order_id', 'in', paid_orders.ids),
                ('payment_type', '=', 'inbound'),
                ('state', 'not in', ['draft', 'cancel', 'cancelled', 'canceled']),
            ])

        for payment in payments:
            self._add_amount(totals, payment.journal_id, payment.amount)

        # Fallback final para el módulo payment_register_statement_v19: líneas de extracto vinculadas al pago.
        if not totals and session.order_ids:
            StmtLine = self.env['account.bank.statement.line'].sudo()
            if 'payment_id' in StmtLine._fields:
                lines = StmtLine.search([
                    ('payment_id.op_sale_order_id', 'in', session.order_ids.ids),
                    ('amount', '>', 0),
                ])
                for line in lines:
                    self._add_amount(totals, line.journal_id, line.amount)

        # Si no hay montos, mostrar al menos los diarios finales de los pedidos en 0.
        if not totals:
            for journal in session.order_ids.mapped('final_payment_journal_id').filtered(lambda j: j):
                self._add_amount(totals, journal, 0.0)

        return totals

    def _get_opening_cash_journal(self, session, totals):
        """Diario donde se suma el fondo inicial, como hace POS con efectivo."""
        cash_items = [data for data in totals.values() if data['journal'].type == 'cash']
        if cash_items:
            return cash_items[0]['journal']
        return self.env['account.journal'].sudo().search([
            ('type', '=', 'cash'),
            ('company_id', '=', session.company_id.id),
        ], limit=1)

    def _get_expected_rendition_rows(self, session):
        """Devuelve las líneas esperadas de rendición ya ordenadas por diario.

        Se usa tanto para abrir el wizard como para recuperar el diario si el
        cliente web no envía un campo readonly de una línea one2many. Esto evita
        el problema de ver una línea en pantalla y que al confirmar llegue sin
        ``payment_journal_id``.
        """
        totals = self._get_session_payment_totals(session)

        # Fondo inicial: se suma solo a un diario de efectivo, igual que POS.
        if session.opening_balance:
            cash_journal = self._get_opening_cash_journal(session, totals)
            if cash_journal:
                self._add_amount(totals, cash_journal, session.opening_balance)

        # Movimientos manuales de efectivo (ingresos/egresos de caja)
        if session.cash_move_ids:
            cash_journal = self._get_opening_cash_journal(session, totals)
            if not cash_journal:
                cash_journal = self.env['account.journal'].sudo().search([
                    ('type', '=', 'cash'),
                    ('company_id', '=', session.company_id.id),
                ], limit=1)
            if cash_journal:
                for move in session.cash_move_ids:
                    signed = move.amount if move.move_type == 'in' else -move.amount
                    self._add_amount(totals, cash_journal, signed)

        rows = []
        for data in sorted(totals.values(), key=lambda x: x['journal'].name or ''):
            journal = data.get('journal')
            if not journal or not journal.id:
                continue
            expected = session.currency_id.round(data['amount']) if session.currency_id else data['amount']
            rows.append({'journal': journal, 'amount_expected': expected})
        return rows

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        session_id = self.env.context.get('default_session_id')
        if not session_id:
            return res
        session = self.env['sale.cashier.session'].browse(session_id)
        if not session.exists():
            return res

        lines = []
        for row in self._get_expected_rendition_rows(session):
            lines.append((0, 0, {
                'payment_journal_id': row['journal'].id,
                'amount_expected': row['amount_expected'],
                'amount_expected_original': row['amount_expected'],
                # Igual que POS: por defecto propone lo esperado, el cajero corrige lo contado.
                'amount_real': row['amount_expected'],
            }))
        res['line_ids'] = lines
        return res

    def _is_zero_amount(self, amount):
        self.ensure_one()
        return self.currency_id.is_zero(amount) if self.currency_id else abs(amount) <= 0.01

    def _recover_missing_journal_lines(self, session):
        """Recupera líneas del wizard que llegaron sin diario por readonly/one2many.

        En algunos clientes web, el ``payment_journal_id`` readonly de una línea
        one2many puede verse en pantalla pero no enviarse al ejecutar el botón.
        Si la cantidad de líneas visibles coincide con lo esperado, reasignamos
        el diario por posición, conservando el importe contado por el cajero.
        """
        candidate_lines = self.line_ids.filtered(
            lambda l: l.payment_journal_id or not self._is_zero_amount(l.amount_expected) or not self._is_zero_amount(l.amount_real)
        )
        missing_journal_lines = candidate_lines.filtered(lambda l: not l.payment_journal_id)
        if not missing_journal_lines:
            return

        expected_rows = self._get_expected_rendition_rows(session)
        if not expected_rows:
            return

        if len(candidate_lines) == len(expected_rows):
            for line, row in zip(candidate_lines.sorted('id'), expected_rows):
                vals = {}
                if not line.payment_journal_id:
                    vals['payment_journal_id'] = row['journal'].id
                if self._is_zero_amount(line.amount_expected):
                    vals['amount_expected'] = row['amount_expected']
                if not line.amount_expected_original:
                    vals['amount_expected_original'] = row['amount_expected']
                if vals:
                    line.write(vals)
        elif len(candidate_lines) == 1 and len(expected_rows) == 1:
            line = candidate_lines[0]
            row = expected_rows[0]
            vals = {'payment_journal_id': row['journal'].id}
            if self._is_zero_amount(line.amount_expected):
                vals['amount_expected'] = row['amount_expected']
            if not line.amount_expected_original:
                vals['amount_expected_original'] = row['amount_expected']
            line.write(vals)

    def action_close_session(self):
        self.ensure_one()
        session = self.session_id
        if session.state != 'open':
            raise UserError(_('La sesión ya fue cerrada.'))

        # Verificar que no haya pedidos sin cobrar vinculados a esta sesión
        pending_orders = self.env['sale.order'].search([
            ('cashier_session_id', '=', session.id),
            ('operational_state', 'in', ['confirmed', 'prepared']),
        ], order='name')
        if pending_orders:
            names = ', '.join(pending_orders.mapped('name'))
            raise UserError(_(
                'No podés cerrar la sesión con pedidos pendientes de cobro.\n\n'
                'Cobrá los siguientes pedidos antes de cerrar:\n%s'
            ) % names)

        self._recover_missing_journal_lines(session)
        valid_lines = self.line_ids.filtered(lambda l: l.payment_journal_id)
        if not valid_lines:
            # Sesión sin movimientos: cerrar directamente sin rendición
            session.write({
                'state': 'closed',
                'closed_date': fields.Datetime.now(),
                'notes': self.notes or False,
            })
            session.message_post(
                body=_('Sesión cerrada por <b>%s</b>. Sin movimientos registrados.')
                % self.env.user.name
            )
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'sale.cashier.close.success.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_session_id': session.id},
            }

        # Validar carry-over contra efectivo realmente contado (no el esperado)
        carry_over = self.currency_id.round(self.carry_over_amount or 0.0) if self.currency_id else (self.carry_over_amount or 0.0)
        if carry_over < 0:
            raise UserError(_('El fondo para la próxima sesión no puede ser negativo.'))
        if carry_over > 0:
            cash_real = sum(
                l.amount_real for l in valid_lines
                if l.payment_journal_id.type == 'cash'
            )
            if self.currency_id:
                cash_real = self.currency_id.round(cash_real)
            if carry_over > cash_real + 0.009:
                raise UserError(_(
                    'El fondo retenido ($%.2f) supera el efectivo contado ($%.2f).\n'
                    'Solo podés retener hasta lo que tenés físicamente en el cajón.'
                ) % (carry_over, cash_real))

        total_expected = sum(valid_lines.mapped('amount_expected'))
        total_real = sum(valid_lines.mapped('amount_real'))
        total_difference = total_real - total_expected
        if self.currency_id:
            total_difference = self.currency_id.round(total_difference)
            total_expected = self.currency_id.round(total_expected)
            total_real = self.currency_id.round(total_real)

        has_difference = any(not self._is_zero_amount(line.difference) for line in valid_lines)
        if has_difference and not (self.notes and self.notes.strip()):
            raise UserError(_(
                'Hay diferencias en la rendición. Ingresá una observación explicando la diferencia antes de cerrar.'
            ))

        session.line_ids.unlink()
        for seq, wiz_line in enumerate(valid_lines, start=1):
            self.env['sale.cashier.session.line'].create({
                'session_id': session.id,
                'sequence': seq * 10,
                'payment_journal_id': wiz_line.payment_journal_id.id,
                'amount_expected': wiz_line.amount_expected,
                'amount_real': wiz_line.amount_real,
                'notes': wiz_line.notes or False,
            })

        session.write({
            'state': 'pending_validation' if has_difference else 'closed',
            'closed_date': fields.Datetime.now(),
            'notes': self.notes or False,
            'carry_over_amount': carry_over,
        })
        session.invalidate_recordset(['total_real', 'total_difference', 'total_expected_rendition'])

        carry_msg = (
            _(' | 💵 Fondo retenido para próxima sesión: %.2f') % carry_over
            if carry_over else ''
        )
        session.message_post(
            body=_('Sesión cerrada por <b>%s</b>. Esperado: %.2f | Rendido: %.2f | Diferencia: %.2f%s') % (
                self.env.user.name, total_expected, total_real, total_difference, carry_msg,
            )
        )
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.cashier.close.success.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_session_id': session.id},
        }


class SaleCashierCloseSuccessWizard(models.TransientModel):
    _name = 'sale.cashier.close.success.wizard'
    _description = 'Confirmación de Cierre de Sesión de Caja'

    session_id = fields.Many2one('sale.cashier.session', required=True, readonly=True)
    cashier_id = fields.Many2one(related='session_id.cashier_id', readonly=True)
    date = fields.Date(related='session_id.date', readonly=True)
    total_orders = fields.Integer(related='session_id.total_orders', readonly=True)
    currency_id = fields.Many2one(related='session_id.currency_id', readonly=True)
    total_collected = fields.Monetary(
        related='session_id.total_collected', readonly=True, currency_field='currency_id',
    )

    def action_print_a4(self):
        self.ensure_one()
        return self.env.ref('sale_op_flow.action_report_cashier_close_details').report_action(self.session_id)

    def action_print_80mm(self):
        self.ensure_one()
        return self.env.ref('sale_op_flow.action_report_cashier_close_80mm').report_action(self.session_id)

    def action_go_to_session(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.cashier.session',
            'res_id': self.session_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
