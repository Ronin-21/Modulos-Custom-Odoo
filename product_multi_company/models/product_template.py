from odoo import fields, models, api

class Product(models.Model):
    _inherit = 'product.template'

    company_ids = fields.Many2many('res.company')