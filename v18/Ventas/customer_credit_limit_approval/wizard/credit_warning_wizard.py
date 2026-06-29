# -*- coding: utf-8 -*-
from odoo import models, fields


class CreditWarningWizard(models.TransientModel):
    _name = 'credit.warning.wizard'
    _description = 'Advertencia de Límite de Crédito'

    sale_order_id = fields.Many2one('sale.order', required=True)
    excess_warning = fields.Monetary(
        string='Exceso sobre advertencia',
        readonly=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='sale_order_id.currency_id',
        readonly=True,
    )

    def action_confirm_anyway(self):
        self.ensure_one()
        return self.sale_order_id.with_context(credit_warning_acknowledged=True).action_confirm()

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}
