# -*- coding: utf-8 -*-
from odoo import api, models


class ReportSofPaymentsPeriod(models.AbstractModel):
    _name = 'report.sale_op_flow.report_sof_payments_period'
    _description = 'Reporte PDF: Cobros por período'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['sof.period.report.wizard'].browse(docids)[:1]
        Report = self.env['sof.payment.report']
        domain = [
            ('date', '>=', wizard.date_from),
            ('date', '<=', wizard.date_to),
        ]
        if wizard.company_id:
            domain.append(('company_id', '=', wizard.company_id.id))

        tender_labels = dict(Report._fields['tender_type'].selection)

        # Resumen por tipo de medio (cobros - reintegros = neto)
        by_tender = []
        total_neto = 0.0
        for tender, amount, count in Report._read_group(
            domain, groupby=['tender_type'], aggregates=['amount:sum', 'payment_count:sum']
        ):
            by_tender.append({
                'label': tender_labels.get(tender, 'Otro'),
                'amount': amount or 0.0,
                'count': count or 0,
            })
            total_neto += amount or 0.0

        # Detalle por sesión (solo cobros netos)
        by_session = []
        for session, amount, count in Report._read_group(
            domain, groupby=['session_id'], aggregates=['amount:sum', 'payment_count:sum']
        ):
            by_session.append({
                'session': session.display_name if session else 'Sin sesión',
                'cashier': session.cashier_id.name if session and session.cashier_id else '',
                'amount': amount or 0.0,
                'count': count or 0,
            })
        by_session.sort(key=lambda s: s['session'])

        return {
            'doc_ids': docids,
            'doc_model': 'sof.period.report.wizard',
            'docs': wizard,
            'date_from': wizard.date_from,
            'date_to': wizard.date_to,
            'company': wizard.company_id or self.env.company,
            'currency': (wizard.company_id or self.env.company).currency_id,
            'by_tender': by_tender,
            'by_session': by_session,
            'total_neto': total_neto,
        }


class ReportSofSessionsPeriod(models.AbstractModel):
    _name = 'report.sale_op_flow.report_sof_sessions_period'
    _description = 'Reporte PDF: Sesiones por período'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['sof.period.report.wizard'].browse(docids)[:1]
        domain = [
            ('date', '>=', wizard.date_from),
            ('date', '<=', wizard.date_to),
        ]
        if wizard.company_id:
            domain.append(('company_id', '=', wizard.company_id.id))
        sessions = self.env['sale.cashier.session'].search(domain, order='date, cashier_id')

        totals = {
            'orders': sum(sessions.mapped('total_orders')),
            'collected': sum(sessions.mapped('total_collected')),
            'cash_in': sum(sessions.mapped('total_cash_in')),
            'cash_out': sum(sessions.mapped('total_cash_out')),
            'expected': sum(sessions.mapped('total_expected_rendition')),
            'real': sum(sessions.mapped('total_real')),
            'difference': sum(sessions.mapped('total_difference')),
        }
        return {
            'doc_ids': docids,
            'doc_model': 'sof.period.report.wizard',
            'docs': wizard,
            'date_from': wizard.date_from,
            'date_to': wizard.date_to,
            'company': wizard.company_id or self.env.company,
            'currency': (wizard.company_id or self.env.company).currency_id,
            'sessions': sessions,
            'totals': totals,
        }
