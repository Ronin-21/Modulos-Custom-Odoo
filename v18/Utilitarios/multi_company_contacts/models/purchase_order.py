# -*- coding: utf-8 -*-
from odoo import api, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"


    def _mcc_check_partner_allowed_purchase(self):
        partners = self.mapped("partner_id").exists()
        if partners:
            partners._mcc_check_business_usage("purchase", "Compras")
        return True

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._mcc_check_partner_allowed_purchase()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if "partner_id" in vals:
            self._mcc_check_partner_allowed_purchase()
        return res

    def button_confirm(self):
        self._mcc_check_partner_allowed_purchase()
        return super().button_confirm()
