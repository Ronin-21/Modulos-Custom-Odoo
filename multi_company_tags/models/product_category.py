from odoo import models, fields


class ProductCategory(models.Model):
    """Extiende categorías de producto para agregar campo de empresa."""
    
    _inherit = 'product.category'
    
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Empresa',
        default=lambda self: self.env.company.id,
        index=True,
        help='La empresa a la que pertenece esta categoría de producto. '
             'Si no se especifica, la categoría será visible para todas las empresas.'
    )