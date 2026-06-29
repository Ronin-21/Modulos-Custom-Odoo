from odoo import models, fields

class PosCategory(models.Model):
    _inherit = "pos.category"

    company_id = fields.Many2one(
        "res.company",
        string="Empresa",
        default=lambda self: self.env.company,
        index=True,
    )

    allowed_company_ids = fields.Many2many(
        "res.company",
        "pos_category_allowed_company_rel",
        "pos_category_id",
        "company_id",
        string="Empresas / Sucursales relacionadas",
    )
