# -*- coding: utf-8 -*-
from odoo import models


class PosSessionFiscalInfo(models.Model):
    _inherit = "pos.session"

    def _loader_params_pos_order(self):
        try:
            params = super()._loader_params_pos_order()
        except AttributeError:
            params = {"search_params": {"fields": []}}

        if not isinstance(params, dict):
            params = {"search_params": {"fields": []}}

        if isinstance(params.get("fields"), list):
            fields_list = params["fields"]
        else:
            search_params = params.setdefault("search_params", {})
            fields_list = search_params.setdefault("fields", [])

        for field in ["invoice_name", "is_fiscal", "payment_method_names"]:
            if field not in fields_list:
                fields_list.append(field)

        return params

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
            "show_ticket_col_coupon",
            "show_ticket_col_state",
            "show_ticket_col_table",
            "show_ticket_col_payments",
            "show_ticket_receipt_fiscal_info",
        ]:
            if field not in fields_list:
                fields_list.append(field)

        return params
