# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PosOrder(models.Model):
    _inherit = 'pos.order'
    
    # Sobrescribir el campo con default=False
    to_invoice = fields.Boolean('To invoice', copy=False, default=False)
    
    @api.model
    def create(self, vals):
        # Asegurar que to_invoice sea False en la creación
        if 'to_invoice' not in vals or vals.get('to_invoice') is None:
            vals['to_invoice'] = False
        return super(PosOrder, self).create(vals)