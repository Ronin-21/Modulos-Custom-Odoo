# -*- coding: utf-8 -*-
from odoo import fields, models

class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    company_ids = fields.Many2many(
        'res.company',
    )
