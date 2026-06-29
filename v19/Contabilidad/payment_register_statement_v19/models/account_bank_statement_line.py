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

    def _get_default_amls_matching_domain(self, allow_draft=False):
        domain = super()._get_default_amls_matching_domain(allow_draft=allow_draft)
        if not self.journal_id:
            return domain

        # Excluir apuntes que están en cuentas de recibos/pagos pendientes de OTROS diarios.
        # Esas cuentas pertenecen a pagos registrados en otro diario y no deben aparecer
        # como candidatos al conciliar el extracto del diario actual.
        all_outstanding_ids = set(
            self.env['account.payment.method.line'].sudo().search([]).payment_account_id.ids
        )
        own_outstanding_ids = set(
            (self.journal_id._get_journal_inbound_outstanding_payment_accounts()
             | self.journal_id._get_journal_outbound_outstanding_payment_accounts()).ids
        )
        foreign_outstanding_ids = all_outstanding_ids - own_outstanding_ids
        if foreign_outstanding_ids:
            domain += [('account_id', 'not in', list(foreign_outstanding_ids))]

        # Excluir apuntes en cuentas transitorias (suspense) de cualquier diario bancario.
        # Las entradas suspense corresponden a otras líneas de extracto pendientes de
        # conciliar, no a pagos, y nunca deben mezclarse en el diálogo de conciliación.
        suspense_ids = (
            self.env['account.journal'].sudo()
            .search([('type', 'in', ['bank', 'cash', 'credit'])])
            .suspense_account_id.ids
        )
        if suspense_ids:
            domain += [('account_id', 'not in', suspense_ids)]

        return domain
