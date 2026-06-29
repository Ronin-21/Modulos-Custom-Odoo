# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    x_ar_withholding_payment_ids = fields.One2many(
        comodel_name="account.payment",
        inverse_name="x_ar_withholding_move_id",
        string="Pagos relacionados",
        readonly=True,
        help="Pagos registrados en la misma operación que generó esta retención.",
    )

    x_ar_is_withholding_move = fields.Boolean(
        string="Es asiento de retención",
        compute="_compute_x_ar_is_withholding_move",
        store=True,
    )

    x_ar_withholding_payment_count = fields.Integer(
        string="Cantidad de pagos",
        compute="_compute_x_ar_is_withholding_move",
        store=True,
    )

    @api.depends("x_ar_withholding_payment_ids")
    def _compute_x_ar_is_withholding_move(self):
        for move in self:
            count = len(move.x_ar_withholding_payment_ids)
            move.x_ar_is_withholding_move = bool(count)
            move.x_ar_withholding_payment_count = count

    def action_view_withholding_payments(self):
        """Abre la lista de pagos relacionados con este asiento de retención."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Pagos relacionados",
            "res_model": "account.payment",
            "view_mode": "list,form",
            "domain": [("x_ar_withholding_move_id", "=", self.id)],
        }