# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PrsAccreditationConfirmWizard(models.TransientModel):
    _name = 'prs.accreditation.confirm.wizard'
    _description = 'Confirmar acreditaciones pendientes'

    journal_id = fields.Many2one(
        'account.journal',
        string='Diario destino',
        required=True,
        readonly=True,
    )
    flow_ids = fields.Many2many(
        'prs.money.flow',
        relation='prs_accr_wiz_flow_rel',
        column1='wizard_id',
        column2='flow_id',
        string='Acreditaciones pendientes',
    )
    flow_count = fields.Integer(compute='_compute_totals', string='Cantidad')
    total_gross_amount = fields.Monetary(
        compute='_compute_totals',
        string='Bruto',
        currency_field='currency_id',
    )
    total_net_amount = fields.Monetary(
        compute='_compute_totals',
        string='Neto a acreditar',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_currency_id',
    )

    @api.depends('journal_id')
    def _compute_currency_id(self):
        for wiz in self:
            wiz.currency_id = (
                wiz.journal_id.currency_id
                or wiz.journal_id.company_id.currency_id
            )

    @api.depends('flow_ids', 'flow_ids.amount_gross', 'flow_ids.amount_signed')
    def _compute_totals(self):
        for wiz in self:
            wiz.flow_count = len(wiz.flow_ids)
            wiz.total_gross_amount = sum(wiz.flow_ids.mapped('amount_gross'))
            wiz.total_net_amount = sum(wiz.flow_ids.mapped('amount_signed'))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        journal_id = (
            self.env.context.get('default_journal_id')
            or self.env.context.get('active_journal_id')
        )
        if journal_id:
            journal = self.env['account.journal'].browse(journal_id).exists()
            if journal:
                flows = journal._prs_prepare_pending_accreditations()
                res['flow_ids'] = [(6, 0, flows.ids)]
        return res

    def _build_success_action(self, count, total, journal_name):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Acreditaciones confirmadas'),
                'message': _(
                    '%(count)d acreditacion(es) confirmada(s) por $%(total).2f en %(journal)s.'
                ) % {'count': count, 'total': total, 'journal': journal_name},
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def _confirm_flows(self, flows):
        flows = flows.filtered(
            lambda f: f.state in ('waiting_accreditation', 'due') and not f.statement_line_id
        )
        if not flows:
            return 0, 0.0
        company_ids = set(self.env.context.get('allowed_company_ids') or [])
        company_ids.update(flows.mapped('company_id').ids)
        company_ids.update(flows.mapped('journal_id.company_id').ids)
        ctx = dict(
            self.env.context,
            allowed_company_ids=list(company_ids),
            prs_force_target_accreditation=True,
        )
        flows.with_context(ctx).action_create_statement_line()
        return len(flows), sum(flows.mapped('amount_signed'))

    def action_confirm_selected(self):
        self.ensure_one()
        if not self.flow_ids:
            raise UserError(_('No hay acreditaciones pendientes para confirmar.'))
        count, total = self._confirm_flows(self.flow_ids)
        if not count:
            raise UserError(_('No hay acreditaciones en estado "Esperando acreditación".'))
        return self._build_success_action(count, total, self.journal_id.display_name)

    def action_confirm_all(self):
        self.ensure_one()
        flows = self.journal_id._prs_prepare_pending_accreditations()
        if not flows:
            raise UserError(_('No hay acreditaciones pendientes para confirmar.'))
        self.write({'flow_ids': [(6, 0, flows.ids)]})
        return self.action_confirm_selected()
