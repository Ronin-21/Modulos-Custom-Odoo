# -*- coding: utf-8 -*-
from odoo import _, fields, models


class SofPrintWizard(models.TransientModel):
    """Wizard post-cobro: pregunta si imprimir la factura."""
    _name = 'sof.print.wizard'
    _description = 'Imprimir factura después del cobro'

    order_id = fields.Many2one('sale.order', required=True, readonly=True)
    invoice_id = fields.Many2one('account.move', readonly=True)
    order_name = fields.Char(related='order_id.name', readonly=True)
    auto_print = fields.Boolean(default=False)

    def action_print_invoice(self):
        self.ensure_one()
        return self.env.ref('account.account_invoices').report_action(self.invoice_id)

    def action_close(self):
        return {'type': 'ir.actions.act_window_close'}
