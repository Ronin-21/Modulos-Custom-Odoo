# -*- coding: utf-8 -*-
from odoo import models, fields

class AccountJournal(models.Model):
    _inherit = 'account.journal'

    show_fiscal_data = fields.Boolean(
        string="Mostrar datos fiscales en el PDF",
        default=True,
        help="Desmarcá esto para diarios como 'Factura X' o 'Comprobantes internos' "
             "para que el reporte no muestre CUIT, IIBB, CAE, etc."
    )
