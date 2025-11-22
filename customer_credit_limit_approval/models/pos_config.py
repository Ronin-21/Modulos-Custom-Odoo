# -*- coding: utf-8 -*-
from odoo import models, fields

class PosConfig(models.Model):
    _inherit = 'pos.config'

    show_partner_balance = fields.Boolean(
        string="Mostrar saldo de clientes en POS",
        help="Si está activo, el POS mostrará la columna 'Saldo' en el selector de clientes.",
        default=False,
    )
