# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import UserError

SUPERVISOR_GROUP = 'sale_op_flow.group_sale_supervisor'


class CclCashierCreditApproval(models.TransientModel):
    _name = 'ccl.cashier.credit.approval'
    _description = 'Autorización de venta en Cuenta Corriente sobre el límite'

    payment_wizard_id = fields.Many2one(
        'sale.cashier.payment.wizard', string='Cobro', required=True, ondelete='cascade'
    )
    sale_order_id = fields.Many2one('sale.order', string='Pedido', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    credit_blocking = fields.Monetary(
        string='Límite de bloqueo', currency_field='currency_id', readonly=True
    )
    projected_debt = fields.Monetary(
        string='Deuda proyectada', currency_field='currency_id', readonly=True
    )
    excess = fields.Monetary(
        string='Exceso', currency_field='currency_id', readonly=True
    )
    supervisor_pin = fields.Char(string='PIN del supervisor')

    def _resolve_supervisor_by_pin(self, pin):
        """Devuelve el empleado supervisor cuyo PIN coincide, o un recordset vacío."""
        pin = (pin or '').strip()
        if not pin:
            return self.env['hr.employee']
        employees = self.env['hr.employee'].sudo().search([('pin', '=', pin)])
        return employees.filtered(
            lambda e: e.user_id and e.user_id.has_group(SUPERVISOR_GROUP)
        )[:1]

    def action_authorize(self):
        """El supervisor autoriza ingresando su PIN/NIP: reanuda el cobro."""
        self.ensure_one()
        supervisor = self._resolve_supervisor_by_pin(self.supervisor_pin)
        if not supervisor:
            raise UserError(_(
                "PIN inválido o el empleado no está autorizado a aprobar crédito.\n"
                "El PIN debe corresponder a un supervisor."
            ))
        return self.payment_wizard_id.with_context(
            ccl_supervisor_authorized=True,
            ccl_authorized_by_employee_id=supervisor.id,
        ).action_confirm_payment()

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}
