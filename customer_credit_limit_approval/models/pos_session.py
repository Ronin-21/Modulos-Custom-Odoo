# models/pos_session.py
from odoo import models

class PosSession(models.Model):
    _inherit = "pos.session"

    def _loader_params_pos_config(self):
        res = super()._loader_params_pos_config()
        fields = res.setdefault("search_params", {}).setdefault("fields", [])
        if "show_partner_balance" not in fields:
            fields.append("show_partner_balance")
        return res
