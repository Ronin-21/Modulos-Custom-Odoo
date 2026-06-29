# -*- coding: utf-8 -*-

from odoo import models


class PosPayment(models.Model):
    _inherit = "pos.payment"

    def _get_receivable_lines_for_invoice_reconciliation(self, receivable_account):
        """Backport de Odoo 19 para elegir las líneas correctas de cobro POS
        al reconciliar una factura.

        Es especialmente importante cuando la cuenta por cobrar del cliente y la
        cuenta por cobrar del POS conviven en el mismo asiento o cuando la orden
        fue facturada después de haber quedado en borrador.
        """
        result = self.env["account.move.line"]
        for payment in self:
            if not payment.account_move_id:
                continue

            currency = payment.currency_id
            is_positive_amount = currency.compare_amounts(payment.amount, 0) > 0

            for line in payment.account_move_id.line_ids:
                if (
                    currency.compare_amounts(line.balance, 0) == 0
                    or line.account_id != receivable_account
                    or line.reconciled
                ):
                    continue

                if is_positive_amount:
                    if currency.compare_amounts(line.balance, 0) < 0:
                        result |= line
                else:
                    if currency.compare_amounts(line.balance, 0) > 0:
                        result |= line
        return result
