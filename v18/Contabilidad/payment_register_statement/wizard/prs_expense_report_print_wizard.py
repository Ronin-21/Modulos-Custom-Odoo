# -*- coding: utf-8 -*-
import json
from odoo import api, fields, models, _

class PrsExpenseReportPrintWizard(models.TransientModel):
    _name = 'prs.expense.report.print.wizard'
    _description = 'Imprimir Reporte de Gastos (PDF)'

    domain_json = fields.Text(string="Dominio", readonly=True)
    group_mode = fields.Selection([
        ('concept', 'Agrupar por concepto'),
        ('date', 'Agrupar por fecha'),
        ('none', 'Sin agrupar'),
    ], string="Agrupación en PDF", default='concept', required=True)

    date_from = fields.Date(string="Desde")
    date_to = fields.Date(string="Hasta")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        domain = self.env.context.get('active_domain') or []
        try:
            res['domain_json'] = json.dumps(domain)
        except Exception:
            res['domain_json'] = '[]'
        return res

    def _get_domain(self):
        self.ensure_one()
        try:
            domain = json.loads(self.domain_json or '[]')
        except Exception:
            domain = []
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        if self.date_to:
            domain.append(('date', '<=', self.date_to))
        return domain

    def _get_payments(self):
        self.ensure_one()
        domain = [('payment_type', '=', 'outbound'), ('is_internal_transfer', '=', False)] + self._get_domain()
        return self.env['account.payment'].search(domain, order='date asc, id asc')

    def _get_grouped_data(self):
        """Return list of groups: {'title': str|False, 'payments': recordset, 'total': float}"""
        self.ensure_one()
        payments = self._get_payments()
        groups = []

        if self.group_mode == 'none':
            return [{
                'title': False,
                'payments': payments,
                'total': sum(payments.mapped('amount')) if payments else 0.0,
            }]

        if self.group_mode == 'date':
            by = {}
            for p in payments:
                key = p.date
                by.setdefault(key, self.env['account.payment'])
                by[key] |= p
            for key in sorted(by.keys()):
                recs = by[key]
                groups.append({
                    'title': fields.Date.to_string(key) if key else _('Sin fecha'),
                    'payments': recs,
                    'total': sum(recs.mapped('amount')) if recs else 0.0,
                })
            return groups

        # default: concept
        by = {}
        for p in payments:
            key = p.prs_expense_concept_id.name if p.prs_expense_concept_id else _('Sin concepto')
            by.setdefault(key, self.env['account.payment'])
            by[key] |= p
        for key in sorted(by.keys()):
            recs = by[key]
            groups.append({
                'title': key,
                'payments': recs,
                'total': sum(recs.mapped('amount')) if recs else 0.0,
            })
        return groups

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('payment_register_statement.report_prs_expense_payments_pdf').report_action(self)
