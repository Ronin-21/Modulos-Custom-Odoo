# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    auc_enabled = fields.Boolean(default=False)

    auc_moment = fields.Selection([
        ('confirm', 'Al confirmar la orden de compra'),
        ('receive', 'Al recibir la mercancía'),
        ('invoice', 'Al validar la factura de proveedor'),
    ], default='receive')

    auc_scope = fields.Selection([
        ('current', 'Solo en la compañía actual'),
        ('all', 'En todas las compañías (Multi-empresa)'),
    ], default='all')

    auc_standard_strategy = fields.Selection([
        ('last', 'Último costo de compra'),
        ('avg_simple', 'Costo promedio (simple, sin stock)'),
    ], default='last')

    auc_avco_replicate = fields.Boolean(default=True)

    auc_propagate_manual_cost = fields.Boolean(default=False)
    auc_propagate_manual_cost_include_avco = fields.Boolean(default=False)

    auc_recalc_bom = fields.Boolean(default=True)
