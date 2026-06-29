# -*- coding: utf-8 -*-
from odoo import models

class PosSession(models.Model):
    _inherit = "pos.session"

    def _loader_params_pos_config(self):
        res = super()._loader_params_pos_config()
        fields_list = res.get("search_params", {}).get("fields", [])
        if "enable_order_ticket" not in fields_list:
            fields_list.append("enable_order_ticket")
        return res
