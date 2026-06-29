# -*- coding: utf-8 -*-
from odoo import api, models


class IrActionsActions(models.Model):
    _inherit = "ir.actions.actions"

    @api.model
    def get_bindings(self, model_name):
        """Adjust the Print menu for stock pickings.

        The backend Print menu is built from model bindings, and in Odoo 18
        the call that builds that menu may arrive without active_id/active_ids.
        Because of that, this module removes the two standard reports that are
        redundant for this customer flow and places the custom internal transfer
        remit at the top of the Print menu.
        """
        result = super().get_bindings(model_name)

        # Work on a copy; the parent result can be cached by Odoo.
        result = {
            binding_type: [dict(action) for action in actions]
            for binding_type, actions in (result or {}).items()
        }

        if model_name != "stock.picking":
            return result

        reports = result.get("report", [])
        if not reports:
            return result

        internal_report = self.env.ref(
            "stock_internal_transfer_remit.action_report_internal_transfer_remit",
            raise_if_not_found=False,
        )
        internal_report_id = internal_report.id if internal_report else False

        hidden_xmlids = {
            "stock.action_report_picking",       # Operaciones de recolección
            "stock.action_report_delivery",      # Recibo de entrega
        }
        hidden_report_names = {
            "stock.report_picking",
            "stock.report_deliveryslip",
        }
        hidden_ids = set()
        for xmlid in hidden_xmlids:
            report_action = self.env.ref(xmlid, raise_if_not_found=False)
            if report_action:
                hidden_ids.add(report_action.id)

        def _get_action_xmlid(action):
            return action.get("xml_id") or action.get("xmlid") or action.get("external_id")

        def _is_hidden_standard_report(action):
            return (
                action.get("id") in hidden_ids
                or _get_action_xmlid(action) in hidden_xmlids
                or action.get("report_name") in hidden_report_names
            )

        def _is_internal_transfer_remit(action):
            return (
                (internal_report_id and action.get("id") == internal_report_id)
                or _get_action_xmlid(action) == "stock_internal_transfer_remit.action_report_internal_transfer_remit"
                or action.get("report_name") == "stock_internal_transfer_remit.itr_remit"
            )

        visible_reports = [
            action for action in reports
            if not _is_hidden_standard_report(action)
        ]

        # Put the custom remit first in Print, preserving the relative order of
        # all remaining reports such as Paquetes, Recibo de devolución and Etiquetas.
        custom_reports = [action for action in visible_reports if _is_internal_transfer_remit(action)]
        other_reports = [action for action in visible_reports if not _is_internal_transfer_remit(action)]
        result["report"] = custom_reports + other_reports

        return result
