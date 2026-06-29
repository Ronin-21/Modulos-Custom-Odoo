from odoo import models, fields

class ProductCategory(models.Model):
    _inherit = "product.category"

    company_id = fields.Many2one(
        "res.company",
        string="Empresa",
        default=lambda self: self.env.company,
        index=True,
    )

    allowed_company_ids = fields.Many2many(
        "res.company",
        "product_category_allowed_company_rel",  # tabla
        "product_category_id",                   # <-- IMPORTANTE (no category_id)
        "company_id",
        string="Empresas / Sucursales relacionadas",
    )
