# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    # Technical compatibility settings for previous builds. They are non-stored
    # to avoid UndefinedColumn during Odoo.sh deployments before upgrade.
    prs_flow_enabled = fields.Boolean(
        string='Usar Flujo de Dinero',
        compute='_compute_prs_flow_journal_settings',
        inverse='_inverse_prs_flow_journal_settings',
        search='_search_prs_flow_enabled',
        readonly=False,
    )
    prs_flow_auto_create_statement = fields.Boolean(
        string='Crear extracto al vencer el flujo',
        compute='_compute_prs_flow_journal_settings',
        inverse='_inverse_prs_flow_journal_settings',
        readonly=False,
    )
    prs_flow_projection_only = fields.Boolean(
        string='Solo proyeccion',
        compute='_compute_prs_flow_journal_settings',
        inverse='_inverse_prs_flow_journal_settings',
        readonly=False,
    )
    prs_flow_statement_policy = fields.Selection(
        selection=[
            ('last_open', 'Usar ultimo estado abierto'),
            ('daily', 'Crear/usar estado diario'),
            ('none', 'Crear linea sin estado'),
        ],
        string='Estados de cuenta para flujo',
        compute='_compute_prs_flow_journal_settings',
        inverse='_inverse_prs_flow_journal_settings',
        readonly=False,
    )
    prs_flow_clearing_account_id = fields.Many2one(
        'account.account',
        string='Cuenta puente flujo',
        compute='_compute_prs_flow_journal_settings',
        inverse='_inverse_prs_flow_journal_settings',
        readonly=False,
        check_company=True,
        help='Cuenta puente o transitoria del diario. No se restringe por tipo en esta mejora.',
    )

    def _prs_flow_journal_param_key(self, field_name):
        self.ensure_one()
        return 'payment_register_statement.money_flow.account_journal.%s.%s' % (field_name, self.id)

    def _prs_get_param_record(self, raw_value, model_name):
        try:
            record_id = int(raw_value or 0)
        except (TypeError, ValueError):
            record_id = 0
        return self.env[model_name].sudo().browse(record_id).exists() if record_id else self.env[model_name]

    def _compute_prs_flow_journal_settings(self):
        ICP = self.env['ir.config_parameter'].sudo()
        for journal in self:
            get = lambda name: ICP.get_param(journal._prs_flow_journal_param_key(name))
            journal.prs_flow_enabled = self._prs_bool_from_param(get('prs_flow_enabled'))
            auto_value = get('prs_flow_auto_create_statement')
            journal.prs_flow_auto_create_statement = True if auto_value in (None, False, '') else self._prs_bool_from_param(auto_value)
            journal.prs_flow_projection_only = self._prs_bool_from_param(get('prs_flow_projection_only'))
            journal.prs_flow_statement_policy = get('prs_flow_statement_policy') or 'daily'
            journal.prs_flow_clearing_account_id = journal._prs_get_param_record(get('prs_flow_clearing_account_id'), 'account.account')

    def _inverse_prs_flow_journal_settings(self):
        ICP = self.env['ir.config_parameter'].sudo()
        for journal in self:
            ICP.set_param(journal._prs_flow_journal_param_key('prs_flow_enabled'), '1' if journal.prs_flow_enabled else '0')
            ICP.set_param(journal._prs_flow_journal_param_key('prs_flow_auto_create_statement'), '1' if journal.prs_flow_auto_create_statement else '0')
            ICP.set_param(journal._prs_flow_journal_param_key('prs_flow_projection_only'), '1' if journal.prs_flow_projection_only else '0')
            ICP.set_param(journal._prs_flow_journal_param_key('prs_flow_statement_policy'), journal.prs_flow_statement_policy or 'daily')
            ICP.set_param(journal._prs_flow_journal_param_key('prs_flow_clearing_account_id'), journal.prs_flow_clearing_account_id.id or '')

    def _search_prs_flow_enabled(self, operator, value):
        if operator not in ('=', '!=', 'in', 'not in'):
            return NotImplemented
        key_prefix = 'payment_register_statement.money_flow.account_journal.prs_flow_enabled.'
        ICP = self.env['ir.config_parameter'].sudo()
        enabled_ids = []
        for param in ICP.search([('key', 'like', key_prefix)]):
            if str(param.value or '').lower() in ('1', 'true', 'yes', 'on'):
                try:
                    enabled_ids.append(int(param.key[len(key_prefix):]))
                except (ValueError, TypeError):
                    pass
        if operator in ('=', 'in'):
            want_true = bool(value) if operator == '=' else any(bool(v) for v in (value or []))
        else:
            want_true = not bool(value) if operator == '!=' else not any(bool(v) for v in (value or []))
        return [('id', 'in', enabled_ids)] if want_true else [('id', 'not in', enabled_ids)]
