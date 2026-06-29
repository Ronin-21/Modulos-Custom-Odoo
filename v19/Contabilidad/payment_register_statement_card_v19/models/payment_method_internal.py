# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PaymentMethod(models.Model):
    _inherit = 'payment.method'

    prs_internal_config_ids = fields.One2many(
        'prs.payment.method.internal.config',
        'payment_method_id',
        string='Ajustes de marca',
        help='Configuracion interna por empresa para marcas/metodos usados por flujo de pagos, POS y futuras integraciones.',
    )
    prs_brand_plan_ids = fields.One2many(
        'prs.payment.method.brand.plan',
        'brand_method_id',
        string='Planes',
        help='Planes/cuotas disponibles para esta marca o metodo de pago.',
    )

    def _prs_get_internal_config(self, company=None):
        self.ensure_one()
        if not self.primary_payment_method_id:
            return self.env['prs.payment.method.internal.config']
        company = company or self.env.company
        return self.prs_internal_config_ids.filtered(lambda c: c.company_id == company)[:1]

    def _prs_prepare_internal_config_dict(self, company=None):
        self.ensure_one()
        config = self._prs_get_internal_config(company)
        if not config:
            return {}
        return config._prs_as_config_dict()


class PrsPaymentMethodInternalConfig(models.Model):
    _name = 'prs.payment.method.internal.config'
    _description = 'Ajustes internos por marca/metodo de pago y empresa'
    _order = 'company_id, id'
    _check_company_auto = True

    payment_method_id = fields.Many2one('payment.method', string='Marca / Metodo', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', string='Empresa', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', related='company_id.currency_id', readonly=True)
    merchant_number = fields.Char(string='Numero de comercio')
    settlement_delay_days = fields.Integer(string='Dias de acreditacion', default=0)
    settlement_day_type = fields.Selection(
        [('calendar', 'Dias corridos'), ('business', 'Dias habiles')],
        string='Tipo de dias',
        default='calendar',
    )
    settlement_journal_id = fields.Many2one(
        'account.journal',
        string='Diario de acreditacion',
        domain="[('type','in',('bank','cash','credit_card'))]",
        check_company=False,
        help='Diario destino sugerido para acreditaciones de esta marca/metodo en esta empresa.',
    )
    fee_percent = fields.Float(string='Comision (%)', default=0.0)
    fee_fixed_amount = fields.Monetary(string='Comision fija', currency_field='currency_id', default=0.0)
    fee_tax_percent = fields.Float(string='IVA comision (%)', default=0.0)
    withholding_percent = fields.Float(string='Retencion/Percepcion (%)', default=0.0)

    _sql_constraints = [
        ('payment_method_company_uniq', 'unique(payment_method_id, company_id)', 'Ya existe una configuracion interna para esta marca/metodo y empresa.'),
    ]

    @api.constrains('payment_method_id')
    def _check_brand_method(self):
        for rec in self:
            if rec.payment_method_id and not rec.payment_method_id.primary_payment_method_id:
                raise ValidationError(_('Los Ajustes Pagos Internos deben configurarse en una Marca/Metodo, no en el metodo de pago primario.'))

    @api.constrains('fee_percent', 'fee_tax_percent', 'withholding_percent')
    def _check_percentages(self):
        for rec in self:
            for value, label in [
                (rec.fee_percent, _('Comision')),
                (rec.fee_tax_percent, _('IVA comision')),
                (rec.withholding_percent, _('Retencion/Percepcion')),
            ]:
                if value < 0 or value > 100:
                    raise ValidationError(_('%s debe estar entre 0 y 100.') % label)

    def _prs_as_config_dict(self):
        self.ensure_one()
        return {
            'merchant_number': self.merchant_number or '',
            'delay_days': self.settlement_delay_days or 0,
            'day_type': self.settlement_day_type or 'calendar',
            'journal': self.settlement_journal_id,
            'fee_percent': self.fee_percent or 0.0,
            'fee_fixed_amount': self.fee_fixed_amount or 0.0,
            'fee_tax_percent': self.fee_tax_percent or 0.0,
            'withholding_percent': self.withholding_percent or 0.0,
        }


class PrsPaymentMethodBrandPlan(models.Model):
    _name = 'prs.payment.method.brand.plan'
    _description = 'Planes por marca/metodo de pago'
    _order = 'sequence, installments, name'
    _check_company_auto = True

    name = fields.Char(string='Plan', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Empresa', default=lambda self: self.env.company, required=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', related='company_id.currency_id', readonly=True)
    brand_method_id = fields.Many2one('payment.method', string='Marca/Metodo', required=True, ondelete='cascade', index=True)
    merchant_number = fields.Char(string='Numero de comercio')
    installments = fields.Integer(string='Cuotas', default=1, required=True)
    percent = fields.Float(string='Recargo del plan (%)', default=0.0)
    prs_apply_commission_surcharge = fields.Boolean(
        string='Aplicar recargo comisiones',
        help='Si esta activo, al usar este plan en POS se traslada al cliente el calculo de comision/IVA/retenciones configurado en el plan.',
    )
    settlement_delay_days = fields.Integer(string='Dias de acreditacion', default=0)
    settlement_day_type = fields.Selection(
        [('calendar', 'Dias corridos'), ('business', 'Dias habiles')],
        string='Tipo de dias',
        default='calendar',
    )
    settlement_journal_id = fields.Many2one(
        'account.journal',
        string='Diario de acreditacion',
        domain="[('type','in',('bank','cash','credit_card'))]",
        check_company=False,
    )
    fee_percent = fields.Float(string='Comision (%)', default=0.0)
    fee_fixed_amount = fields.Monetary(string='Comision fija', currency_field='currency_id', default=0.0)
    fee_tax_percent = fields.Float(string='IVA comision (%)', default=0.0)
    withholding_percent = fields.Float(string='Retencion/Percepcion (%)', default=0.0)

    # Aliases backward-compatible con versiones anteriores de POS.
    prs_settlement_delay_days = fields.Integer(related='settlement_delay_days', readonly=False)
    prs_settlement_day_type = fields.Selection(related='settlement_day_type', readonly=False)
    prs_settlement_journal_id = fields.Many2one(related='settlement_journal_id', readonly=False)
    prs_fee_percent = fields.Float(related='fee_percent', readonly=False)
    prs_fee_fixed_amount = fields.Monetary(related='fee_fixed_amount', readonly=False, currency_field='currency_id')
    prs_fee_tax_percent = fields.Float(related='fee_tax_percent', readonly=False)
    prs_withholding_percent = fields.Float(related='withholding_percent', readonly=False)
    # Cuentas contables legacy de versiones intermedias de POS — no se muestran en vistas nuevas.
    prs_fee_account_id = fields.Many2one('account.account', string='Cuenta gasto comision', check_company=True)
    prs_fee_tax_account_id = fields.Many2one('account.account', string='Cuenta IVA comision', check_company=True)
    prs_withholding_account_id = fields.Many2one('account.account', string='Cuenta retenciones', check_company=True)

    @api.constrains('brand_method_id')
    def _check_brand_method(self):
        for plan in self:
            if plan.brand_method_id and not plan.brand_method_id.primary_payment_method_id:
                raise ValidationError(_('Los planes deben configurarse en una Marca/Metodo, no en el metodo de pago primario.'))

    @api.constrains('installments', 'percent', 'fee_percent', 'fee_tax_percent', 'withholding_percent')
    def _check_values(self):
        for plan in self:
            if plan.installments < 1:
                raise ValidationError(_('El numero de cuotas debe ser al menos 1.'))
            for value, label in [
                (plan.percent, _('Recargo del plan')),
                (plan.fee_percent, _('Comision')),
                (plan.fee_tax_percent, _('IVA comision')),
                (plan.withholding_percent, _('Retencion/Percepcion')),
            ]:
                if value < 0 or value > 100:
                    raise ValidationError(_('%s debe estar entre 0 y 100.') % label)

    def _prs_as_config_dict(self):
        self.ensure_one()
        return {
            'merchant_number': self.merchant_number or '',
            'delay_days': self.settlement_delay_days or 0,
            'day_type': self.settlement_day_type or 'calendar',
            'journal': self.settlement_journal_id,
            'fee_percent': self.fee_percent or 0.0,
            'fee_fixed_amount': self.fee_fixed_amount or 0.0,
            'fee_tax_percent': self.fee_tax_percent or 0.0,
            'withholding_percent': self.withholding_percent or 0.0,
            'plan_percent': self.percent or 0.0,
            'apply_commission_surcharge': bool(self.prs_apply_commission_surcharge),
        }
