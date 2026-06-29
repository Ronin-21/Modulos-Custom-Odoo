# -*- coding: utf-8 -*-
from odoo import fields, models
from .stock_picking import INSTALLATION_MOVE_TYPE_SELECTION


class StockMove(models.Model):
    _inherit = 'stock.move'

    installation_line_id = fields.Many2one(
        'sale.installation.material.line', string='Línea de control de instalación',
        copy=False, index=True, ondelete='set null')
    installation_move_type = fields.Selection(
        INSTALLATION_MOVE_TYPE_SELECTION, string='Movimiento de instalación', copy=False)
