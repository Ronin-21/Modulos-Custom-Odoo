# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class CashierCashMoveWizard(models.TransientModel):
    _name = 'sale.cashier.cash.move.wizard'
    _description = 'Ingreso / Egreso de Efectivo en Caja'

    session_id = fields.Many2one(
        'sale.cashier.session', string='Sesión', required=True, readonly=True,
    )
    move_type = fields.Selection(
        [('in', 'Ingreso de efectivo'), ('out', 'Egreso de efectivo')],
        string='Tipo', required=True,
    )
    amount = fields.Monetary(string='Monto', required=True, currency_field='currency_id')
    reason = fields.Char(string='Motivo', required=True)
    currency_id = fields.Many2one(related='session_id.currency_id', readonly=True)

    def _get_open_session(self):
        Session = self.env['sale.cashier.session'].sudo()
        ctx_id = (
            self.env.context.get('default_session_id')
            or self.env.context.get('sof_cashier_session_id')
        )
        if ctx_id:
            s = Session.browse(ctx_id).exists()
            if s and s.state == 'open':
                return s
        session = Session.search([
            ('state', '=', 'open'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        return session or Session.search([('state', '=', 'open')], limit=1)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        session = self._get_open_session()
        if not session:
            raise UserError(_(
                'No hay sesión de caja abierta.\n'
                'Abrí una desde Caja → Abrir sesión de caja.'
            ))
        res['session_id'] = session.id
        return res

    def action_confirm(self):
        self.ensure_one()
        if not self.amount or self.amount <= 0:
            raise UserError(_('El monto debe ser mayor a cero.'))
        if not self.reason or not self.reason.strip():
            raise UserError(_('Ingresá un motivo para el movimiento.'))

        self.env['sale.cashier.cash.move'].create({
            'session_id': self.session_id.id,
            'move_type': self.move_type,
            'amount': self.amount,
            'reason': self.reason.strip(),
        })

        label = _('Ingreso de efectivo') if self.move_type == 'in' else _('Egreso de efectivo')
        self.session_id.message_post(
            body=_('<b>%s</b>: %s %s — %s (registrado por %s)') % (
                label,
                self.session_id.currency_id.symbol or '$',
                '{:,.2f}'.format(self.amount),
                self.reason,
                self.env.user.name,
            )
        )
        return {'type': 'ir.actions.act_window_close'}
