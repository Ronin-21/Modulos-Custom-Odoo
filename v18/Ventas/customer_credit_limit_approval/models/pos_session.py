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

    def _loader_params_res_partner(self):
        res = super()._loader_params_res_partner()
        fields = res.setdefault("search_params", {}).setdefault("fields", [])
        # evita duplicar y asegura lo que usa el front
        for f in ("credit", "debit", "credit_check", "credit_blocking"):
            if f not in fields:
                fields.append(f)
        return res
