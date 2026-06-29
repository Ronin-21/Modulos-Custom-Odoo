# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Cuentas contables predeterminadas para comisiones de tarjetas.
    # Sirven de fallback cuando el diario puente no tiene cuentas propias.
    # Almacenadas en ir.config_parameter con las mismas claves que PRS nativo
    # para preservar datos ya configurados.

    prs_default_flow_fee_account_id = fields.Many2one(
        'account.account',
        string='Cuenta comisiones predeterminada',
        compute='_compute_prs_card_company_accounts',
        inverse='_inverse_prs_card_company_accounts',
        readonly=False,
        help='Cuenta de gasto usada para comisiones cuando el diario puente no tiene cuenta propia.',
    )
    prs_default_flow_fee_tax_account_id = fields.Many2one(
        'account.account',
        string='Cuenta IVA comisión predeterminada',
        compute='_compute_prs_card_company_accounts',
        inverse='_inverse_prs_card_company_accounts',
        readonly=False,
        help='Activo corriente o gasto, según el tratamiento del IVA de la comisión.',
    )
    prs_default_flow_withholding_account_id = fields.Many2one(
        'account.account',
        string='Cuenta retenciones predeterminada',
        compute='_compute_prs_card_company_accounts',
        inverse='_inverse_prs_card_company_accounts',
        readonly=False,
        help='Activo corriente o pasivo corriente, según si la retención es sufrida o a pagar.',
    )

    def _compute_prs_card_company_accounts(self):
        ICP = self.env['ir.config_parameter'].sudo()
        Account = self.env['account.account'].sudo()
        fee_fields = (
            'prs_default_flow_fee_account_id',
            'prs_default_flow_fee_tax_account_id',
            'prs_default_flow_withholding_account_id',
        )
        for company in self:
            for field_name in fee_fields:
                raw = ICP.get_param(company._prs_money_flow_param_key(field_name))
                try:
                    account_id = int(raw or 0)
                except (TypeError, ValueError):
                    account_id = 0
                company[field_name] = Account.browse(account_id).exists() if account_id else self.env['account.account']

    def _inverse_prs_card_company_accounts(self):
        ICP = self.env['ir.config_parameter'].sudo()
        for company in self:
            ICP.set_param(
                company._prs_money_flow_param_key('prs_default_flow_fee_account_id'),
                company.prs_default_flow_fee_account_id.id or '',
            )
            ICP.set_param(
                company._prs_money_flow_param_key('prs_default_flow_fee_tax_account_id'),
                company.prs_default_flow_fee_tax_account_id.id or '',
            )
            ICP.set_param(
                company._prs_money_flow_param_key('prs_default_flow_withholding_account_id'),
                company.prs_default_flow_withholding_account_id.id or '',
            )

    def _prs_validate_card_account(self, field_name, allowed_types, label):
        for company in self:
            account = company[field_name]
            if not account:
                continue
            if account.account_type not in allowed_types:
                raise ValidationError(_(
                    '%s: la cuenta "%s" no es válida. Tipos permitidos: %s.'
                ) % (label, account.display_name, ', '.join(allowed_types)))
            account_companies = getattr(account, 'company_ids', False)
            if account_companies and company not in account_companies:
                raise ValidationError(_(
                    '%s: la cuenta "%s" no está disponible para la compañía "%s".'
                ) % (label, account.display_name, company.display_name))

    @api.constrains(
        'prs_default_flow_fee_account_id',
        'prs_default_flow_fee_tax_account_id',
        'prs_default_flow_withholding_account_id',
    )
    def _check_prs_card_default_accounts(self):
        for company in self:
            company._prs_validate_card_account(
                'prs_default_flow_fee_account_id', ('expense',), _('Cuenta comisiones predeterminada')
            )
            company._prs_validate_card_account(
                'prs_default_flow_fee_tax_account_id',
                ('asset_current', 'expense'),
                _('Cuenta IVA comisión predeterminada'),
            )
            company._prs_validate_card_account(
                'prs_default_flow_withholding_account_id',
                ('asset_current', 'liability_current'),
                _('Cuenta retenciones predeterminada'),
            )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    prs_default_flow_fee_account_id = fields.Many2one(
        'account.account',
        string='Cuenta comisiones predeterminada',
        related='company_id.prs_default_flow_fee_account_id',
        readonly=False,
        domain="[('active', '=', True), ('account_type', '=', 'expense')]",
    )
    prs_default_flow_fee_tax_account_id = fields.Many2one(
        'account.account',
        string='Cuenta IVA comisión predeterminada',
        related='company_id.prs_default_flow_fee_tax_account_id',
        readonly=False,
        domain="[('active', '=', True), ('account_type', 'in', ('asset_current', 'expense'))]",
    )
    prs_default_flow_withholding_account_id = fields.Many2one(
        'account.account',
        string='Cuenta retenciones predeterminada',
        related='company_id.prs_default_flow_withholding_account_id',
        readonly=False,
        domain="[('active', '=', True), ('account_type', 'in', ('asset_current', 'liability_current'))]",
    )
