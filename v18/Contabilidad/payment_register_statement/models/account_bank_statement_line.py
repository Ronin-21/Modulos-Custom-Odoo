# -*- coding: utf-8 -*-
from odoo import models, fields, api
from .prs_utils import prs_is_pos, prs_vals_look_like_pos


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    prs_expense_concept_id = fields.Many2one(
        'prs.expense.concept',
        string="Concepto de gasto",
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        # POS: si la línea de extracto viene del POS y no tiene contacto,
        # asignamos el partner de la compañía.
        is_pos_ctx = prs_is_pos(self.env)
        for vals in vals_list:
            if vals.get('partner_id'):
                continue

            # Si está vinculada a un pago, heredamos su partner
            payment_id = vals.get('payment_id')
            if payment_id:
                payment = self.env['account.payment'].browse(payment_id)
                if payment and payment.exists():
                    if payment.partner_id:
                        vals['partner_id'] = payment.partner_id.id
                        continue
                    if payment.company_id and payment.company_id.partner_id:
                        vals['partner_id'] = payment.company_id.partner_id.id
                        continue

            if is_pos_ctx or prs_vals_look_like_pos(vals):
                company = self.env['res.company'].browse(
                    vals.get('company_id') or self.env.company.id
                )
                if company and company.partner_id:
                    vals['partner_id'] = company.partner_id.id

        # Si la línea viene vinculada a un pago y no trae concepto, heredarlo del pago.
        lines = super().create(vals_list)
        for line, vals in zip(lines, vals_list):
            if not vals.get('prs_expense_concept_id') and getattr(line, 'payment_id', False):
                payment = line.payment_id
                if getattr(payment, 'prs_expense_concept_id', False):
                    line.prs_expense_concept_id = payment.prs_expense_concept_id
        return lines
