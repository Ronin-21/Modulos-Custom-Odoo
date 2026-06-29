# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    commission_percent = fields.Float(
        string='Comisión personalizada (%)',
        digits=(5, 2),
        default=0.0,
        help='Si es > 0, prevalece sobre el porcentaje por defecto de la '
             'configuración general.',
    )
    use_custom_commission = fields.Boolean(
        string='Usar comisión personalizada',
        default=False,
    )