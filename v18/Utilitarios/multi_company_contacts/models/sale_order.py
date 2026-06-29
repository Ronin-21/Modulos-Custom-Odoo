# -*- coding: utf-8 -*-
from odoo import api, models


class SaleOrder(models.Model):
    _inherit = "sale.order"


    def _mcc_check_partner_allowed_sale(self):
        partners = self.mapped("partner_id").exists()
        if partners:
            partners._mcc_check_business_usage("sale", "Ventas")
        return True

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._mcc_check_partner_allowed_sale()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if "partner_id" in vals:
            self._mcc_check_partner_allowed_sale()
        return res

    def action_confirm(self):
        self._mcc_check_partner_allowed_sale()
        return super().action_confirm()
