# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    picking_id = fields.Many2one(
        'stock.picking',
        string='Recepción vinculada',
        help='Recepción desde la que se generó esta línea de factura.',
    )
