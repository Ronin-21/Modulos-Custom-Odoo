# -*- coding: utf-8 -*-
from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    prs_expense_concept_id = fields.Many2one(
        'prs.expense.concept',
        string="Concepto de gasto predeterminado",
        help="Se aplicará por defecto en facturas/pagos de proveedor si no se elige uno.",
    )
