# -*- coding: utf-8 -*-
from odoo import api, models


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies.mapped("partner_id")._mcc_auto_configure_system_contacts()
        return companies

    def write(self, vals):
        res = super().write(vals)
        if "partner_id" in vals or "parent_id" in vals or "name" in vals:
            self.env["res.partner"]._mcc_auto_configure_system_contacts()
        return res
