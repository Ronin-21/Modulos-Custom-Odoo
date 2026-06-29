# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # Some account_reports caret options try to open the related payment using `action_param='payment_id'`.
    # In some Odoo builds, account.move.line doesn't expose `payment_id`, which causes:
    #   KeyError: 'payment_id'
    # when the user clicks "Ver pago" in the report.
    payment_id = fields.Many2one(
        comodel_name="account.payment",
        string="Pago",
        compute="_compute_payment_id",
        readonly=True,
    )

    @api.depends("move_id")
    def _compute_payment_id(self):
        for line in self:
            move = line.move_id
            # Be defensive across versions: `payment_id` may not exist on account.move in some builds.
            pid = getattr(move, "payment_id", False) if move else False
            line.payment_id = pid or False
