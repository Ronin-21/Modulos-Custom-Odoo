# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    is_sof_adjustment_line = fields.Boolean(
        string='Línea de ajuste (SOF)', default=False, copy=False,
    )
