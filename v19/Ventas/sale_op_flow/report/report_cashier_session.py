# -*- coding: utf-8 -*-
from functools import partial
from odoo import models, api
from odoo.tools.misc import formatLang as _formatLang


class ReportCashierSession(models.AbstractModel):
    _name = 'report.sale_op_flow.report_cashier_close_details'
    _description = 'Reporte de Cierre de Sesión de Caja (A4)'

    @api.model
    def _get_report_values(self, docids, data=None):
        sessions = self.env['sale.cashier.session'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'sale.cashier.session',
            'docs': [self._build_doc(s) for s in sessions],
            'formatLang': partial(_formatLang, self.env),
        }

    def _build_doc(self, session):
        payments = self.env['account.payment'].sudo().search([
            ('op_cashier_session_id', '=', session.id),
            ('payment_type', '=', 'inbound'),
            ('state', 'not in', ['draft', 'cancelled', 'canceled']),
        ])

        journals = {}
        for p in payments:
            jid = p.journal_id.id
            if jid not in journals:
                journals[jid] = {
                    'journal': p.journal_id,
                    'count': 0,
                    'total': 0.0,
                    'plans': {},
                }
            jd = journals[jid]
            jd['count'] += 1
            jd['total'] += p.amount

            plan = p.op_financing_plan_id
            pk = plan.id if plan else 0
            if pk not in jd['plans']:
                label = ''
                if plan and plan.adjustment_type != 'none' and plan.adjustment_rate:
                    sign = '+' if plan.adjustment_type == 'surcharge' else '-'
                    label = ' (%s%d%%)' % (sign, round(plan.adjustment_rate))
                jd['plans'][pk] = {
                    'name': (plan.name + label) if plan else 'Sin plan',
                    'count': 0,
                    'total': 0.0,
                    'coupons': [],
                }
            pd = jd['plans'][pk]
            pd['count'] += 1
            pd['total'] += p.amount
            if p.op_coupon_number:
                pd['coupons'].append(p.op_coupon_number)

        journal_list = sorted(
            [
                dict(jd, plan_lines=sorted(jd['plans'].values(), key=lambda pl: pl['name']))
                for jd in journals.values()
            ],
            key=lambda j: j['journal'].name,
        )

        cash_moves = session.cash_move_ids.sorted('date')
        state_labels = dict(session._fields['state'].selection)
        return {
            'session': session,
            'state_label': state_labels.get(session.state, session.state),
            'journal_lines': journal_list,
            'total_count': sum(j['count'] for j in journal_list),
            'total_amount': sum(j['total'] for j in journal_list),
            'cash_moves': cash_moves,
            'total_cash_in': sum(m.amount for m in cash_moves if m.move_type == 'in'),
            'total_cash_out': sum(m.amount for m in cash_moves if m.move_type == 'out'),
        }


class ReportCashierSession80mm(models.AbstractModel):
    _name = 'report.sale_op_flow.report_cashier_close_80mm'
    _inherit = 'report.sale_op_flow.report_cashier_close_details'
    _description = 'Reporte de Cierre de Sesión de Caja (80mm)'
