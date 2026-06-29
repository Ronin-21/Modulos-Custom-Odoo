# -*- coding: utf-8 -*-
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    prs_money_flow_ids = fields.One2many(
        'prs.money.flow',
        'payment_id',
        string='Flujos de dinero PRS',
        readonly=True,
    )
    prs_money_flow_count = fields.Integer(
        string='Flujos PRS',
        compute='_compute_prs_money_flow_count',
    )

    def _compute_prs_money_flow_count(self):
        for payment in self:
            payment.prs_money_flow_count = len(payment.prs_money_flow_ids)

    def _prs_get_flow_expected_date(self):
        self.ensure_one()
        return self.date or fields.Date.context_today(self)

    def _prs_get_flow_journal(self):
        self.ensure_one()
        return self.journal_id

    def _prs_get_money_flow_entries(self):
        """Return PRS money-flow values for this payment.

        Base module is opt-in through Ajustes > Contabilidad > Flujo de Pagos
        and account.journal.prs_payment_register_enabled, so existing automatic
        statement behavior remains unchanged until enabled.
        Extensions (Argentina/POS) can override this method and return entries
        even when the journal flag is disabled.
        """
        self.ensure_one()
        journal = self._prs_get_flow_journal()
        if not journal or not self.company_id.prs_money_flow_enabled or not getattr(journal, 'prs_payment_register_enabled', False):
            return []
        direction = 'inbound' if self.payment_type == 'inbound' else 'outbound'
        expected_date = self._prs_get_flow_expected_date()
        return [self._prs_prepare_money_flow_vals(
            journal=journal,
            expected_date=expected_date,
            amount=self.amount,
            direction=direction,
            label=self._prs_get_payment_label(),
            flow_type='payment',
            unique_suffix='payment',
        )]

    def _prs_prepare_money_flow_vals(self, journal, expected_date, amount, direction, label, flow_type='payment', unique_suffix=None, extra=None):
        self.ensure_one()
        vals = {
            'company_id': journal.company_id.id,
            'journal_id': journal.id,
            'payment_id': self.id,
            'partner_id': self.partner_id.id or False,
            'currency_id': self.currency_id.id or journal.company_id.currency_id.id,
            'source_model': 'account.payment',
            'source_res_id': self.id,
            'flow_type': flow_type,
            'direction': direction,
            'label': label or self.name or 'Pago',
            'origin_date': self.date or fields.Date.context_today(self),
            'expected_date': expected_date or self.date or fields.Date.context_today(self),
            'amount_gross': abs(amount or 0.0),
            'auto_create_statement': bool(getattr(journal, 'auto_extract_enabled', False)),
            'projection_only': False,
            'unique_key': 'account.payment:%s:%s:%s:%s:%s' % (
                self.id,
                unique_suffix or flow_type,
                journal.id,
                expected_date or self.date or fields.Date.context_today(self),
                direction,
            ),
        }
        if extra:
            vals.update(extra)
        return vals

    def _prs_create_statement_lines(self):
        self.ensure_one()
        entries = self._prs_get_money_flow_entries()
        if not entries:
            return super()._prs_create_statement_lines()

        Flow = self.env['prs.money.flow'].sudo()
        for vals in entries:
            flow = Flow.with_company(self.company_id or self.env.company)._prs_create_or_get(vals)
            if flow._prs_should_create_statement_now():
                flow.action_create_statement_line()
            else:
                _logger.info(
                    'PRS: flujo de dinero proyectado para pago %s en %s (%s).',
                    self.display_name,
                    flow.expected_date,
                    flow.label,
                )
        return True

    def action_open_prs_money_flows(self):
        self.ensure_one()
        action = self.env.ref('payment_register_statement_v19.action_prs_money_flow').read()[0]
        action['domain'] = [('payment_id', '=', self.id)]
        action['context'] = {
            'default_payment_id': self.id,
            'default_partner_id': self.partner_id.id,
            'default_company_id': self.company_id.id,
        }
        return action

    def action_draft(self):
        flows_to_cancel = self.mapped('prs_money_flow_ids').filtered(
            lambda f: not f.statement_line_id and f.state in ('planned', 'due', 'manual_review')
        )
        res = super().action_draft()
        if flows_to_cancel:
            flows_to_cancel.action_cancel()
        return res

    def unlink(self):
        flows_to_cancel = self.mapped('prs_money_flow_ids').filtered(
            lambda f: not f.statement_line_id and f.state in ('planned', 'due', 'manual_review')
        )
        if flows_to_cancel:
            flows_to_cancel.action_cancel()
        return super().unlink()
