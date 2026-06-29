# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    op_sale_order_id = fields.Many2one('sale.order', string='Pedido de venta', copy=False, index=True)
    op_cashier_session_id = fields.Many2one('sale.cashier.session', string='Sesión de caja', copy=False, index=True)
    op_financing_plan_id = fields.Many2one('sale.financing.plan', string='Plan de pago', copy=False)
    op_coupon_number = fields.Char(string='Nº Cupón / Voucher', copy=False)
