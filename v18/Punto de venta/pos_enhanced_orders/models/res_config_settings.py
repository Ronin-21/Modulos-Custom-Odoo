# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_confirm_draft_invoices_on_closing = fields.Boolean(
        related="pos_config_id.confirm_draft_invoices_on_closing",
        readonly=False,
    )

    pos_auto_reconcile_pos_invoices_on_closing = fields.Boolean(
        related="pos_config_id.auto_reconcile_pos_invoices_on_closing",
        readonly=False,
    )
