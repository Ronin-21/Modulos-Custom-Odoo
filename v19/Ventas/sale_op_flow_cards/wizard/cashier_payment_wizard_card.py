# -*- coding: utf-8 -*-
from odoo import api, models


class SaleCashierPaymentWizard(models.TransientModel):
    _inherit = 'sale.cashier.payment.wizard'

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order_id = res.get('sale_order_id')
        if not order_id or 'payment_line_ids' not in fields_list:
            return res
        order = self.env['sale.order'].browse(order_id)
        if not order.prs_card_id and not order.prs_installment_id:
            return res
        updated = []
        for cmd in res.get('payment_line_ids', []):
            if cmd[0] == 0:
                vals = dict(cmd[2])
                if order.prs_card_id:
                    vals['prs_card_id'] = order.prs_card_id.id
                if order.prs_installment_id:
                    vals['prs_installment_id'] = order.prs_installment_id.id
                    coef = order.prs_installment_id._sof_effective_coefficient()
                    if coef > 1.0:
                        amount = round(
                            order.amount_total + order.amount_untaxed * (coef - 1.0), 2
                        )
                        vals['amount'] = amount
                        vals['cash_received'] = amount
                    card_journal = (
                        order.prs_installment_id.settlement_journal_id
                        or order.prs_card_id.settlement_journal_id
                    )
                    if card_journal:
                        vals['payment_journal_id'] = card_journal.id
                updated.append((0, 0, vals))
            else:
                updated.append(cmd)
        res['payment_line_ids'] = updated
        return res

    @api.depends(
        'payment_mode',
        'cash_line_ids.amount', 'cash_line_ids.financing_plan_id',
        'bank_line_ids.amount', 'bank_line_ids.financing_plan_id',
        'bank_line_ids.prs_installment_id',
        'check_line_ids.amount', 'check_line_ids.financing_plan_id',
        'cc_line_ids.amount', 'cc_line_ids.financing_plan_id',
        'sale_order_id.amount_total',
        'sale_order_id.amount_untaxed',
    )
    def _compute_multi_totals(self):
        super()._compute_multi_totals()
        for wiz in self:
            all_lines = wiz.cash_line_ids | wiz.bank_line_ids | wiz.check_line_ids | wiz.cc_line_ids
            card_lines = all_lines.filtered(lambda l: l.prs_installment_id)
            if not card_lines:
                continue
            if wiz.payment_mode == 'single':
                base = wiz.order_amount_untaxed
                order_total = wiz.order_amount_total
                adjustment = sum(
                    base * (max(l.prs_installment_id._sof_effective_coefficient(), 1.0) - 1.0)
                    for l in card_lines
                )
                multi_total = sum(all_lines.mapped('amount'))
                wiz.total_adjustment = adjustment
                wiz.total_to_collect = order_total + adjustment
                wiz.multi_remaining = wiz.total_to_collect - multi_total
                wiz.multi_is_balanced = abs(wiz.multi_remaining) <= 0.01
                wiz.has_surcharge = adjustment > 0.01
            else:
                # Modo multi: sumar recargos de tarjeta al surcharge_amount ya calculado
                card_surcharge = 0.0
                for line in card_lines:
                    coef = line.prs_installment_id._sof_effective_coefficient()
                    amt = line.amount or 0.0
                    if coef > 1.0 and amt > 0:
                        card_surcharge += amt - round(amt / coef, 2)
                card_surcharge = round(card_surcharge, 2)
                if card_surcharge <= 0.01:
                    continue
                total_surcharge = round((wiz.surcharge_amount or 0.0) + card_surcharge, 2)
                multi_total = sum(all_lines.mapped('amount'))
                order_total = wiz.order_amount_total
                # "Falta asignar" se calcula contra (pedido + recargo total),
                # ya que el recargo se suma a la factura al confirmar.
                effective_invoice = order_total + total_surcharge
                surplus = multi_total - effective_invoice
                check_excess = round(surplus, 2) if surplus > 0.01 else 0.0
                wiz.surcharge_amount = total_surcharge
                wiz.has_surcharge = True
                wiz.multi_remaining = effective_invoice - multi_total
                wiz.multi_is_balanced = wiz.multi_remaining <= 0.01
                wiz.check_excess_amount = check_excess if check_excess > 0.01 else 0.0
                wiz.has_check_excess = check_excess > 0.01
