# -*- coding: utf-8 -*-
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import models, fields


class MrpBomMultiCompany(models.Model):
    _inherit = "mrp.bom"

    allowed_company_ids = fields.Many2many(
        comodel_name="res.company",
        relation="mrp_bom_allowed_company_rel",
        column1="bom_id",
        column2="company_id",
        string="Empresas / Sucursales relacionadas",
        help=(
            "Empresas adicionales que pueden ver y utilizar esta lista de "
            "materiales cuando la BoM es global (sin empresa definida)."
        ),
    )
