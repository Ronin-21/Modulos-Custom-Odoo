# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # IMPORTANT: these fields are intentionally non-stored and backed by
    # ir.config_parameter.  Adding stored columns on res.company can break the
    # web client before a module upgrade can run, because Odoo reads
    # res.company while loading menus/session info.
    prs_money_flow_enabled = fields.Boolean(
        string='Flujo de Pagos',
        compute='_compute_prs_money_flow_settings',
        inverse='_inverse_prs_money_flow_settings',
        search='_search_prs_money_flow_enabled',
        readonly=False,
    )

    def _prs_money_flow_param_key(self, field_name):
        self.ensure_one()
        return 'payment_register_statement.%s.company_%s' % (field_name, self.id)

    @api.model
    def _prs_bool_from_param(self, value):
        return str(value or '').lower() in ('1', 'true', 'yes', 'on')

    def _compute_prs_money_flow_settings(self):
        ICP = self.env['ir.config_parameter'].sudo()
        for company in self:
            company.prs_money_flow_enabled = self._prs_bool_from_param(
                ICP.get_param(company._prs_money_flow_param_key('prs_money_flow_enabled'))
            )

    def _inverse_prs_money_flow_settings(self):
        ICP = self.env['ir.config_parameter'].sudo()
        for company in self:
            ICP.set_param(
                company._prs_money_flow_param_key('prs_money_flow_enabled'),
                '1' if company.prs_money_flow_enabled else '0',
            )
        try:
            self.env['ir.ui.menu'].clear_caches()
        except Exception:
            pass

    def _search_prs_money_flow_enabled(self, operator, value):
        if operator not in ('=', '!=', 'in', 'not in'):
            return NotImplemented
        key_prefix = 'payment_register_statement.prs_money_flow_enabled.company_'
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
