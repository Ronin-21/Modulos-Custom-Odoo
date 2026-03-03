# -*- coding: utf-8 -*-
from odoo import models


class PosSessionFiscalInfo(models.Model):
    _inherit = "pos.session"

    def _loader_params_pos_order(self):
        res = super()._loader_params_pos_order()
        fields_ = res["search_params"].setdefault("fields", [])
        extra = [
            "invoice_name",
            "is_fiscal",
            "invoice_state",
            "invoice_state_label",
            "payment_method_names",
        ]
        for f in extra:
            if f not in fields_:
                fields_.append(f)
        return res

    def _loader_params_pos_config(self):
        params = super()._loader_params_pos_config()

        if isinstance(params, dict) and isinstance(params.get("fields"), list):
            fields_list = params["fields"]
        else:
            search_params = params.setdefault("search_params", {})
            fields_list = search_params.setdefault("fields", [])

        for field in [
            "show_ticket_col_date",
            "show_ticket_col_receipt",
            "show_ticket_col_order",
            "show_ticket_col_client",
            "show_ticket_col_cashier",
            "show_ticket_col_total",
            "show_ticket_col_state",
            "show_ticket_col_table",
            "show_ticket_col_payments",
            "show_ticket_receipt_fiscal_info",
            "show_ticket_col_invoice_state",  # ✅ FALTABA ESTE CAMPO
        ]:
            if field not in fields_list:
                fields_list.append(field)

        return params