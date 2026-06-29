from odoo import models, fields


class PosCategory(models.Model):
    """Extiende categorías POS para agregar campo de empresa."""
    
    _inherit = 'pos.category'
    
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Empresa',
        default=lambda self: self.env.company.id,
        index=True,
        help='La empresa a la que pertenece esta categoría del POS. '
             'Si no se especifica, la categoría será visible para todas las empresas.'
    )