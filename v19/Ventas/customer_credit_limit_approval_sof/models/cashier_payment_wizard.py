# -*- coding: utf-8 -*-
from odoo import models


class SaleCashierPaymentWizard(models.TransientModel):
    _inherit = 'sale.cashier.payment.wizard'

    def action_confirm_payment(self):
        """Intercepta el cobro: si hay Cuenta Corriente sobre el límite, pide la
        autorización con PIN de un supervisor antes de cobrar.

        - Dentro del límite ('ok') o cliente sin crédito: deja seguir al flujo
          normal; la red de seguridad de _complete_multi_payment bloquea lo que
          corresponda.
        - Sobre el límite ('confirm'): abre el wizard de autorización por PIN.
        """
        self.ensure_one()
        if not self.env.context.get('ccl_supervisor_authorized'):
            cc_lines = self.payment_line_ids.filtered(lambda l: l.line_type == 'cc')
            if cc_lines:
                order = self.sale_order_id
                cc_amount = sum(line.amount for line in cc_lines)
                if order._ccl_cc_status(cc_amount)[0] == 'confirm':
                    return order._ccl_open_cashier_confirm(self, cc_amount)
        return super().action_confirm_payment()
