# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import UserError

SUPERVISOR_GROUP = 'sale_op_flow.group_sale_supervisor'


class SofSupervisorPinWizard(models.TransientModel):
    _name = 'sof.supervisor.pin.wizard'
    _description = 'Autorización de supervisor por PIN (NC / Cambio)'

    order_id = fields.Many2one(
        'sale.order', string='Pedido', required=True, readonly=True, ondelete='cascade',
    )
    action_type = fields.Selection([
        ('exchange', 'Cambio / Devolución'),
    ], string='Acción', required=True, readonly=True, default='exchange')
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
        """El supervisor autoriza con su PIN: reanuda la acción solicitada."""
        self.ensure_one()
        supervisor = self._resolve_supervisor_by_pin(self.supervisor_pin)
        if not supervisor:
            raise UserError(_(
                'PIN inválido o el empleado no es supervisor.\n'
                'El PIN debe corresponder a un supervisor del flujo.'
            ))
        order = self.order_id.with_context(sof_supervisor_authorized=True)
        return order.action_open_exchange_wizard()

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}
