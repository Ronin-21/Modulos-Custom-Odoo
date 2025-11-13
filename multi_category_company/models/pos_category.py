from odoo import models, fields

class PosCategory(models.Model):
    _inherit = 'pos.category'

    company_id = fields.Many2one(
        'res.company',
        string='Empresa Relacionada',
        default=lambda self: self.env.company.id,
        index=True,
        help='La empresa a la que pertenece esta categoría del POS.'
    )
