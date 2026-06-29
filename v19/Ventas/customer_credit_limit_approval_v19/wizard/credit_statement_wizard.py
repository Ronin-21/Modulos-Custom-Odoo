# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CreditStatementWizard(models.TransientModel):
    _name = 'credit.statement.wizard'
    _description = 'Estado de Cuenta del Cliente'

    partner_id = fields.Many2one('res.partner', readonly=True)
    currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_currency_id',
    )
    amount_due_accounting = fields.Monetary(
        string='Deuda contable (facturas abiertas)',
        currency_field='currency_id',
        compute='_compute_credit_data',
    )
    amount_due_sale = fields.Monetary(
        string='Ventas confirmadas sin facturar',
        currency_field='currency_id',
        compute='_compute_credit_data',
    )
    amount_due = fields.Monetary(
        string='Deuda total',
        currency_field='currency_id',
        compute='_compute_credit_data',
    )
    credit_warning = fields.Monetary(
        string='Límite de advertencia',
        currency_field='currency_id',
        compute='_compute_credit_data',
    )
    credit_blocking = fields.Monetary(
        string='Límite de bloqueo',
        currency_field='currency_id',
        compute='_compute_credit_data',
    )
    utilization_pct = fields.Float(
        string='Utilización del límite',
        digits=(6, 1),
        compute='_compute_credit_data',
    )

    @api.depends('partner_id')
    def _compute_currency_id(self):
        default = self.env.company.currency_id
        for rec in self:
            rec.currency_id = rec.partner_id.company_id.currency_id or default

    @api.depends('partner_id')
    def _compute_credit_data(self):
        for rec in self:
            p = rec.partner_id
            rec.amount_due_accounting = p.amount_due_accounting
            rec.amount_due_sale = p.amount_due_sale
            rec.amount_due = p.amount_due
            rec.credit_warning = p.credit_warning
            rec.credit_blocking = p.credit_blocking
            rec.utilization_pct = (
                round(p.amount_due / p.credit_blocking * 100, 1)
                if p.credit_blocking else 0.0
            )

    def action_print(self):
        self.ensure_one()
        return self.env.ref(
            'customer_credit_limit_approval_v19.action_report_partner_account_statement'
        ).report_action(self.partner_id)
