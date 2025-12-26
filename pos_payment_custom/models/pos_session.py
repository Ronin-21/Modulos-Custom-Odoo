from odoo import models


class PosSession(models.Model):
    _inherit = "pos.session"

    def _loader_params_pos_payment_method(self):
        res = super()._loader_params_pos_payment_method()
        search_params = res.get("search_params") or {}
        fields = search_params.get("fields") or []
        if not isinstance(fields, list):
            fields = list(fields)

        for fname in (
            "apply_adjustment",
            "adjustment_type",
            "adjustment_value",
            "adjustment_product_id",
            "adjustment_options",
        ):
            if fname not in fields:
                fields.append(fname)

        search_params["fields"] = fields
        res["search_params"] = search_params
        return res
