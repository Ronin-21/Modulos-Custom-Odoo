# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class AccountJournalAccreditationControl(models.Model):
    _inherit = 'account.journal'

    prs_accreditation_control = fields.Boolean(
        string='Control de acreditaciones',
        compute='_compute_prs_accreditation_control',
        inverse='_inverse_prs_accreditation_control',
        search='_search_prs_accreditation_control',
        readonly=False,
        help=(
            'Activado: las acreditaciones requieren confirmación manual desde el wizard '
            '(el cron NO crea extractos automáticamente). '
            'Desactivado: el cron crea extractos y concilia automáticamente al vencer el plazo.'
        ),
    )
    prs_accreditation_pending_count = fields.Integer(
        string='Acreditaciones pendientes',
        compute='_compute_prs_accreditation_pending_count',
    )

    def _prs_accreditation_param_key(self):
        self.ensure_one()
        return 'payment_register_statement_card_v19.accreditation_control.%s' % self.id

    def _compute_prs_accreditation_control(self):
        ICP = self.env['ir.config_parameter'].sudo()
        for journal in self:
            val = ICP.get_param(journal._prs_accreditation_param_key())
            journal.prs_accreditation_control = str(val or '').lower() in ('1', 'true')

    def _inverse_prs_accreditation_control(self):
        ICP = self.env['ir.config_parameter'].sudo()
        for journal in self:
            enabled = journal.prs_accreditation_control
            ICP.set_param(journal._prs_accreditation_param_key(), '1' if enabled else '0')
            # Sincronizar con prs_flow_auto_create_statement del módulo base:
            # control manual activado → deshabilitar creación automática de extractos, y viceversa.
            auto_key = journal._prs_flow_journal_param_key('prs_flow_auto_create_statement')
            ICP.set_param(auto_key, '0' if enabled else '1')

    def _search_prs_accreditation_control(self, operator, value):
        # Odoo 19 optimizes '= True' → 'in [True]' before calling search methods.
        if operator not in ('=', '!=', 'in', 'not in'):
            return NotImplemented
        journals = self.sudo().search([])
        enabled_ids = journals.filtered(lambda j: j.prs_accreditation_control).ids
        if operator in ('=', 'in'):
            want_true = bool(value) if operator == '=' else any(bool(v) for v in (value or []))
        else:
            want_true = not bool(value) if operator == '!=' else not any(bool(v) for v in (value or []))
        if want_true:
            return [('id', 'in', enabled_ids)]
        return [('id', 'not in', enabled_ids)]

    def _prs_prepare_pending_accreditations(self):
        self.ensure_one()
        today = fields.Date.today()
        return self.env['prs.money.flow'].search([
            ('journal_id', '=', self.id),
            ('state', 'in', ('waiting_accreditation', 'due')),
            ('statement_line_id', '=', False),
            ('expected_date', '<=', today),
        ])

    @api.depends('prs_accreditation_control')
    def _compute_prs_accreditation_pending_count(self):
        for journal in self:
            if not journal.prs_accreditation_control:
                journal.prs_accreditation_pending_count = 0
            else:
                journal.prs_accreditation_pending_count = len(
                    journal._prs_prepare_pending_accreditations()
                )

    def action_open_prs_accreditations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Acreditaciones pendientes'),
            'res_model': 'prs.accreditation.confirm.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_journal_id': self.id,
                'active_journal_id': self.id,
            },
        }
