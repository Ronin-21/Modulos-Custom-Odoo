# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.osv import expression


class PosSession(models.Model):
    _inherit = "pos.session"

    def _loader_params_res_partner(self):
        """Compatibilidad con loaders POS de versiones anteriores.

        En POS el filtro comercial debe aplicarse siempre. No usamos bypass por
        administrador porque el POS puede estar abierto con usuario técnico/admin
        mientras opera un cajero/empleado.
        """
        params = super()._loader_params_res_partner() if hasattr(super(), "_loader_params_res_partner") else {"search_params": {"domain": []}}
        domain = params.get("search_params", {}).get("domain", [])
        Partner = self.env["res.partner"]
        pos_domain = Partner._mcc_business_domain("pos")
        current_user_partner_domain = [("id", "=", self.env.user.partner_id.id)]
        params.setdefault("search_params", {})["domain"] = expression.OR([
            current_user_partner_domain,
            expression.AND([domain, pos_domain]),
        ])
        return params


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _mcc_check_partner_allowed_pos(self):
        partners = self.mapped("partner_id").exists()
        if partners:
            partners._mcc_check_business_usage("pos", "POS")
        return True

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._mcc_check_partner_allowed_pos()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if "partner_id" in vals:
            self._mcc_check_partner_allowed_pos()
        return res

    def action_pos_order_paid(self):
        self._mcc_check_partner_allowed_pos()
        return super().action_pos_order_paid()
