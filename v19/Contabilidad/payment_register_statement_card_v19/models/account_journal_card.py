# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    # ── Vinculación con procesador de tarjetas ───────────────────────────────

    prs_card_provider_id = fields.Many2one(
        'prs.card.provider',
        string='Procesador de tarjetas',
        domain="[('company_id', '=', company_id)]",
        ondelete='set null',
        help='Si se configura, este diario es un diario puente de tarjetas. '
             'Al registrar pagos aparecerá la selección de tarjeta y plan.',
    )

    # ── Diario puente (migrado desde PRS nativo) ─────────────────────────────
    # prs_is_bridge_journal se deriva directamente de prs_card_provider_id.
    # No requiere configuración manual: si hay procesador → es diario puente.

    prs_is_bridge_journal = fields.Boolean(
        string='Diario puente',
        compute='_compute_prs_is_bridge_journal',
        store=True,
        help='Verdadero cuando el diario está vinculado a un procesador de tarjetas. '
             'Habilita las cuentas contables de comisiones e IVA específicas de este diario.',
    )

    # ── Cuentas de comisiones por diario (migradas desde PRS nativo) ─────────
    # Almacenadas en ir.config_parameter con las mismas claves que antes,
    # garantizando compatibilidad con datos ya configurados.

    prs_flow_fee_account_id = fields.Many2one(
        'account.account',
        string='Cuenta comisiones',
        compute='_compute_prs_card_bridge_accounts',
        inverse='_inverse_prs_card_bridge_accounts',
        readonly=False,
        check_company=True,
        domain="[('active', '=', True), ('account_type', '=', 'expense')]",
        help='Cuenta de gasto donde se imputa la comisión del procesador de tarjetas.',
    )
    prs_flow_fee_tax_account_id = fields.Many2one(
        'account.account',
        string='Cuenta IVA comisión',
        compute='_compute_prs_card_bridge_accounts',
        inverse='_inverse_prs_card_bridge_accounts',
        readonly=False,
        check_company=True,
        domain="[('active', '=', True), ('account_type', 'in', ('asset_current', 'expense'))]",
        help='Cuenta donde se imputa el IVA de la comisión.',
    )
    prs_flow_withholding_account_id = fields.Many2one(
        'account.account',
        string='Cuenta retenciones',
        compute='_compute_prs_card_bridge_accounts',
        inverse='_inverse_prs_card_bridge_accounts',
        readonly=False,
        check_company=True,
        domain="[('active', '=', True), ('account_type', 'in', ('asset_current', 'liability_current'))]",
        help='Cuenta donde se imputan las retenciones aplicadas en la liquidación.',
    )

    # ── Compute / Inverse ────────────────────────────────────────────────────

    @api.depends('prs_card_provider_id')
    def _compute_prs_is_bridge_journal(self):
        for journal in self:
            journal.prs_is_bridge_journal = bool(journal.prs_card_provider_id)

    def _compute_prs_card_bridge_accounts(self):
        ICP = self.env['ir.config_parameter'].sudo()
        for journal in self:
            get = lambda name: ICP.get_param(journal._prs_flow_journal_param_key(name))
            journal.prs_flow_fee_account_id = journal._prs_get_param_record(
                get('prs_flow_fee_account_id'), 'account.account'
            )
            journal.prs_flow_fee_tax_account_id = journal._prs_get_param_record(
                get('prs_flow_fee_tax_account_id'), 'account.account'
            )
            journal.prs_flow_withholding_account_id = journal._prs_get_param_record(
                get('prs_flow_withholding_account_id'), 'account.account'
            )

    def _inverse_prs_card_bridge_accounts(self):
        ICP = self.env['ir.config_parameter'].sudo()
        for journal in self:
            ICP.set_param(
                journal._prs_flow_journal_param_key('prs_flow_fee_account_id'),
                journal.prs_flow_fee_account_id.id or '',
            )
            ICP.set_param(
                journal._prs_flow_journal_param_key('prs_flow_fee_tax_account_id'),
                journal.prs_flow_fee_tax_account_id.id or '',
            )
            ICP.set_param(
                journal._prs_flow_journal_param_key('prs_flow_withholding_account_id'),
                journal.prs_flow_withholding_account_id.id or '',
            )

    # ── Validación de cuentas ────────────────────────────────────────────────

    def _prs_validate_flow_account(self, field_name, allowed_types, label):
        for journal in self:
            account = journal[field_name]
            if not account:
                continue
            if account.account_type not in allowed_types:
                raise ValidationError(_(
                    '%s: la cuenta "%s" no es válida. Tipos permitidos: %s.'
                ) % (label, account.display_name, ', '.join(allowed_types)))
            account_companies = getattr(account, 'company_ids', False)
            if account_companies and journal.company_id and journal.company_id not in account_companies:
                raise ValidationError(_(
                    '%s: la cuenta "%s" no está disponible para la compañía "%s".'
                ) % (label, account.display_name, journal.company_id.display_name))

    @api.constrains('prs_flow_fee_account_id', 'prs_flow_fee_tax_account_id', 'prs_flow_withholding_account_id')
    def _check_prs_card_flow_accounts(self):
        for journal in self:
            journal._prs_validate_flow_account(
                'prs_flow_fee_account_id', ('expense',), _('Cuenta comisiones')
            )
            journal._prs_validate_flow_account(
                'prs_flow_fee_tax_account_id', ('asset_current', 'expense'), _('Cuenta IVA comisión')
            )
            journal._prs_validate_flow_account(
                'prs_flow_withholding_account_id',
                ('asset_current', 'liability_current'),
                _('Cuenta retenciones'),
            )
