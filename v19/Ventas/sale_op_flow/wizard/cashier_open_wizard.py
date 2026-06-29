from odoo import models, fields, api, _
from odoo.exceptions import UserError


class CashierOpenWizard(models.TransientModel):
    """
    Wizard de apertura de sesión de caja — similar al opening_control del POS.
    El cajero ingresa el fondo inicial y una nota opcional, luego confirma
    para abrir la sesión. La sesión queda bloqueada para edición manual.
    """
    _name = 'sale.cashier.open.wizard'
    _description = 'Apertura de Sesión de Caja'

    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
        readonly=True,
    )
    initial_fund = fields.Monetary(
        string='Fondo inicial en caja',
        currency_field='currency_id',
        default=0.0,
        help='Monto en efectivo con el que inicia la sesión.',
    )
    carry_over_source_session_id = fields.Many2one(
        'sale.cashier.session',
        string='Sesión anterior',
        readonly=True,
    )
    carry_over_amount_proposed = fields.Monetary(
        string='Retenido al cierre anterior',
        currency_field='currency_id',
        readonly=True,
    )
    fund_difference = fields.Monetary(
        string='Diferencia',
        currency_field='currency_id',
        default=0.0,
        help='Diferencia entre el fondo ingresado y el carry-over propuesto.',
    )
    is_supervisor = fields.Boolean(compute='_compute_is_supervisor')
    carry_over_change_reason = fields.Char(
        string='Motivo del ajuste',
        help='Obligatorio cuando el fondo ingresado difiere del carry-over propuesto.',
    )
    opening_notes = fields.Text(string='Nota de apertura')
    cashier_id = fields.Many2one(
        'res.users',
        string='Cajero',
        default=lambda self: self.env.user,
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        readonly=True,
    )

    @api.depends_context('uid')
    def _compute_is_supervisor(self):
        is_sup = self.env.user.has_group('sale_op_flow.group_sale_supervisor')
        for rec in self:
            rec.is_supervisor = is_sup

    @api.onchange('initial_fund', 'carry_over_amount_proposed')
    def _onchange_fund_difference(self):
        self.fund_difference = self.initial_fund - (self.carry_over_amount_proposed or 0.0)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        last_session = self.env['sale.cashier.session'].search([
            ('cashier_id', '=', self.env.uid),
            ('company_id', '=', self.env.company.id),
            ('state', 'in', ('closed', 'pending_validation', 'validated')),
            ('carry_over_amount', '>', 0),
        ], order='closed_date desc', limit=1)
        if last_session:
            res['carry_over_source_session_id'] = last_session.id
            res['carry_over_amount_proposed'] = last_session.carry_over_amount
            res['initial_fund'] = last_session.carry_over_amount
            res['fund_difference'] = 0.0
        return res

    def action_open_session(self):
        """Crea la sesión y la abre."""
        existing = self.env['sale.cashier.session'].search([
            ('state', '=', 'open'),
            ('cashier_id', '=', self.cashier_id.id),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if existing:
            raise UserError(_(
                'Ya tenés una sesión abierta: %s\n'
                'Cerrá esa sesión antes de abrir una nueva.'
            ) % existing.name)

        # Control de carry-over
        carry_proposed = self.carry_over_amount_proposed or 0.0
        carry_changed = (
            self.carry_over_source_session_id
            and carry_proposed > 0
            and abs(self.initial_fund - carry_proposed) > 0.009
        )
        if carry_changed:
            if not self.env.user.has_group('sale_op_flow.group_sale_supervisor'):
                raise UserError(_(
                    'El fondo inicial fue pre-cargado desde el turno anterior ($%.2f).\n'
                    'Solo un supervisor puede modificarlo.'
                ) % carry_proposed)
            if not (self.carry_over_change_reason and self.carry_over_change_reason.strip()):
                raise UserError(_('Ingresá el motivo del ajuste antes de continuar.'))

        session = self.env['sale.cashier.session'].create({
            'cashier_id': self.cashier_id.id,
            'company_id': self.company_id.id,
            'opening_balance': self.initial_fund,
            'state': 'open',
        })

        session.message_post(
            body=_('💰 Sesión abierta por <b>%s</b>. Fondo inicial: $%.2f')
            % (self.env.user.name, self.initial_fund)
        )

        if carry_changed:
            diff = carry_proposed - self.initial_fund
            direction = _('reducido') if diff > 0 else _('aumentado')
            msg = _(
                '⚠️ Fondo de carry-over <b>%s</b> por supervisor <b>%s</b>: '
                '$%.2f → $%.2f | Motivo: %s'
            ) % (direction, self.env.user.name, carry_proposed, self.initial_fund,
                 self.carry_over_change_reason)
            session.message_post(body=msg)
            self.carry_over_source_session_id.message_post(body=_(
                '⚠️ El fondo retenido ($%.2f) fue %s a $%.2f al abrir la siguiente sesión. '
                'Supervisor: <b>%s</b>. Motivo: %s'
            ) % (carry_proposed, direction, self.initial_fund,
                 self.env.user.name, self.carry_over_change_reason))

            # Si el fondo fue reducido: crear egreso contable por la diferencia
            if diff > 0:
                self._create_carry_over_withdrawal(session, diff)

        if self.opening_notes:
            session.message_post(body=_('📋 Nota de apertura: %s') % self.opening_notes)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Sesión de Caja'),
            'res_model': 'sale.cashier.session',
            'res_id': session.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _create_carry_over_withdrawal(self, session, amount):
        """Registra un egreso en el diario de efectivo cuando el supervisor
        reduce el carry-over. El dinero salió físicamente del cajón antes
        de abrir la sesión y debe quedar reflejado contablemente."""
        cash_journal = self.env['account.journal'].sudo().search([
            ('type', '=', 'cash'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not cash_journal:
            session.message_post(body=_(
                '⚠️ No se encontró un diario de efectivo para registrar el egreso de $%.2f. '
                'Registralo manualmente.'
            ) % amount)
            return

        ref = _('Retiro carry-over apertura — %s — Supervisor: %s') % (
            self.carry_over_change_reason, self.env.user.name
        )
        st_line = self.env['account.bank.statement.line'].sudo().with_company(
            self.company_id
        ).create({
            'journal_id': cash_journal.id,
            'date': fields.Date.context_today(self),
            'amount': -amount,
            'payment_ref': ref,
        })
        move_name = st_line.move_id.name if st_line.move_id else '—'
        session.message_post(body=_(
            '📒 Egreso de caja registrado: <b>$%.2f</b> | Asiento: %s | Motivo: %s'
        ) % (amount, move_name, self.carry_over_change_reason))
        self.carry_over_source_session_id.message_post(body=_(
            '📒 Egreso de caja por retiro de carry-over al abrir sesión siguiente: '
            '<b>$%.2f</b> | Asiento: %s'
        ) % (amount, move_name))
