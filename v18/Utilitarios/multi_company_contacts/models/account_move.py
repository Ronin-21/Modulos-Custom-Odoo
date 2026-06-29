# -*- coding: utf-8 -*-
from odoo import api, models


class AccountMove(models.Model):
    _inherit = "account.move"


    def _mcc_check_partner_allowed_accounting(self):
        moves = self.filtered(lambda m: m.partner_id and m.is_invoice(include_receipts=True))
        partners = moves.mapped("partner_id").exists()
        if partners:
            partners._mcc_check_business_usage("accounting", "Contabilidad")
        return True

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves._mcc_check_partner_allowed_accounting()
        return moves

    def write(self, vals):
        res = super().write(vals)
        if "partner_id" in vals or "move_type" in vals:
            self._mcc_check_partner_allowed_accounting()
        return res

    def action_post(self):
        self._mcc_check_partner_allowed_accounting()
        return super().action_post()


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def _mcc_check_partner_allowed_payment(self):
        payments = self.filtered(lambda p: p.partner_id)
        partners = payments.mapped("partner_id").exists()
        if partners:
            partners._mcc_check_business_usage("accounting", "Contabilidad")
        return True

    @api.model_create_multi
    def create(self, vals_list):
        payments = super().create(vals_list)
        payments._mcc_check_partner_allowed_payment()
        return payments

    def write(self, vals):
        res = super().write(vals)
        if "partner_id" in vals:
            self._mcc_check_partner_allowed_payment()
        return res

    def action_post(self):
        self._mcc_check_partner_allowed_payment()
        return super().action_post()
