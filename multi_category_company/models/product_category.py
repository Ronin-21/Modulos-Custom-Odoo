from odoo import models, fields

class ProductCategory(models.Model):
    _inherit = 'product.category'
    
    company_id = fields.Many2one(
        'res.company',
        string='Empresa Relacionada',
        default=lambda self: self.env.company.id,
        index=True,
        help='La empresa a la que pertenece esta categoría de producto.'
    )