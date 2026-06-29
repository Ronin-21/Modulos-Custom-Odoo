# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

# Nombre del método de pago POS que representa "Cuenta Corriente".
# Ajustar si en la base de datos el método tiene otro nombre.
POS_CC_PAYMENT_METHOD_NAME = 'Cuenta Corriente'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    amount_due_pos = fields.Monetary(
        string='POS Cuenta Corriente pendiente',
        currency_field='company_currency_id',
        compute='_compute_credit_components',
        store=False,
        help='Tickets de PdV pagados con Cuenta Corriente que aún no tienen asiento contable.',
    )

    @api.depends('credit', 'debit')
    def _compute_credit_components(self):
        """Extiende el compute base para sumar la deuda de tickets POS en Cuenta Corriente."""
        super()._compute_credit_components()

        pm_cc = self.env['pos.payment.method'].search(
            [('name', '=', POS_CC_PAYMENT_METHOD_NAME)], limit=1
        )
        if not pm_cc:
            _logger.warning(
                "customer_credit_limit_approval_pos: no se encontró el método de pago POS "
                "'%s'. amount_due_pos quedará en 0.",
                POS_CC_PAYMENT_METHOD_NAME,
            )
            for partner in self:
                partner.amount_due_pos = 0.0
            return

        PosOrder = self.env['pos.order']
        for partner in self:
            pos_orders = PosOrder.search([
                ('partner_id', '=', partner.id),
                ('state', '!=', 'cancel'),
                ('amount_total', '>', 0),
                ('payment_ids.payment_method_id', '=', pm_cc.id),
                ('account_move', '=', False),
            ])
            pos_amount = sum(pos_orders.mapped('amount_total'))
            partner.amount_due_pos = pos_amount
            partner.amount_due = partner.amount_due + pos_amount
