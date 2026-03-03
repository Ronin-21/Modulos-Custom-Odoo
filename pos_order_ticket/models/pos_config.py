# -*- coding: utf-8 -*-
from odoo import fields, models

class PosConfig(models.Model):
    _inherit = "pos.config"

    enable_order_ticket = fields.Boolean(
        string="Habilitar ticket de pedido (comanda)",
        help="Muestra un botón en el POS para imprimir un ticket de pedido (sin precios).",
        default=False,
    )
    