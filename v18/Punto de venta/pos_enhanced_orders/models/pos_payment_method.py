# -*- coding: utf-8 -*-

from odoo import fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    is_credit_sale = fields.Boolean(
        string="Es cuenta corriente",
        help=(
            "Indica que este método de pago del POS no representa un cobro inmediato. "
            "El importe quedará abierto en la factura como saldo a cobrar al cliente y "
            "no deberá exigirse conciliación al cierre por esa parte."
        ),
    )
