# -*- coding: utf-8 -*-
from odoo import models

class PosSession(models.Model):
    _inherit = "pos.session"

    # Inyectamos campos adicionales de la configuración al payload del POS
    def _loader_params_pos_config(self):
        params = super()._loader_params_pos_config()
        fields = params.get("search_params", {}).setdefault("fields", [])
        for f in ["show_partner_balance", "user_can_see_balance"]:
            if f not in fields:
                fields.append(f)
        return params

    # (opcional pero recomendado) cargar saldo-base de partner para poder mostrarlo
    def _loader_params_res_partner(self):
        params = super()._loader_params_res_partner()
        fields = params.get("search_params", {}).setdefault("fields", [])
        for f in ["credit", "debit", "credit_check", "credit_blocking"]:
            if f not in fields:
                fields.append(f)
        return params
