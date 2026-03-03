# -*- coding: utf-8 -*-
from odoo import models, fields


class PosConfigFiscalInfo(models.Model):
    _inherit = "pos.config"

    # Columnas existentes
    show_ticket_col_client = fields.Boolean(string="Columna: Cliente", default=True)
    show_ticket_col_cashier = fields.Boolean(string="Columna: Cajero", default=True)
    show_ticket_col_total = fields.Boolean(string="Columna: Total", default=True)
    show_ticket_col_coupon = fields.Boolean(string="Columna: Cupón", default=True)
    show_ticket_col_state = fields.Boolean(string="Columna: Estado", default=True)
    show_ticket_col_table = fields.Boolean(string="Columna: Mesa", default=True)
    show_ticket_col_date = fields.Boolean(string="Columna: Fecha", default=True)
    show_ticket_col_order = fields.Boolean(string="Columna: Número de orden", default=True)
    show_ticket_col_receipt = fields.Boolean(
        string="Columna: Número de recibo",
        default=True,
    )

    # Modificaciones visuales
    show_ticket_receipt_fiscal_info = fields.Boolean(
        string="Modificar 'Número de recibo' (Factura / Sin factura)",
        default=True,
        help="Si se desactiva, el POS no modifica la columna 'Número de recibo' y queda como Odoo estándar.",
    )

    # Nueva columna
    show_ticket_col_payments = fields.Boolean(
        string="Columna: Pagos (métodos de pago)",
        default=True,
        help="Muestra una columna con los métodos de pago usados en la orden (Ej: Efectivo, Tarjeta).",
    )
