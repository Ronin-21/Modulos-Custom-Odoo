# -*- coding: utf-8 -*-
from odoo import models, fields, _, api


class CreditApprovalWizard(models.TransientModel):
    _name = 'credit.approval.wizard'
    _description = 'Diálogo de Aprobación de Límite de Crédito'

    sale_order_id = fields.Many2one('sale.order', required=True)
    difference = fields.Monetary(
        string='Exceso de Límite',
        readonly=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='sale_order_id.currency_id',
        readonly=True,
    )

    def action_send_for_approval(self):
        """
        Envía la orden a aprobación de crédito.
        """
        self.ensure_one()
        order = self.sale_order_id

        # manda la orden al estado de aprobación (esto ya postea y notifica)
        order.send_credit_limit_approval()

        # por si en algún momento se quita del order, lo reforzamos acá
        if hasattr(order, '_create_review_activity_for_managers'):
            order._create_review_activity_for_managers(self.difference)

        # Recargar la orden
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': order.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_cancel(self):
        """
        Cancela sin enviar a aprobación.
        """
        return {'type': 'ir.actions.act_window_close'}
