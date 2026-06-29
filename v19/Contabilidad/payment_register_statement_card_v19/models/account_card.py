# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountCard(models.Model):
    """Tarjeta de crédito/débito con configuración de acreditación y comisiones para PRS.
    Incluye el modelo base de card_installment (ADHOC SA) extendido con campos propios."""
    _name = 'account.card'
    _description = 'Credit Card'

    name = fields.Char('Nombre', required=True)
    company_id = fields.Many2one(
        'res.company',
        index=True,
        help='Dejar vacío para que la tarjeta sea global y esté disponible en todas las empresas.',
    )
    active = fields.Boolean(default=True)
    installment_ids = fields.One2many('account.card.installment', 'card_id', string='Planes')

    provider_id = fields.Many2one(
        'prs.card.provider',
        string='Proveedor',
        ondelete='set null',
        index=True,
        help='Proveedor que procesa los pagos con esta tarjeta (Payway, Clover, Mercado Pago, etc.).',
    )

    # Vinculacion con payment.method nativo de Odoo
    payment_method_id = fields.Many2one(
        'payment.method',
        string='Metodo de pago (PRS)',
        ondelete='set null',
        domain="[('primary_payment_method_id', '!=', False)]",
        help='Marca/Metodo de pago de Odoo vinculado a esta tarjeta. '
             'Permite conectar configuracion Payway con el flujo de pagos de Payment Register.',
    )

    # Configuracion PRS por defecto para esta tarjeta (los planes pueden sobrescribir)
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
        domain="[('type', '=', 'bank')]",
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='company_id.currency_id',
        readonly=True,
    )
    fee_percent = fields.Float(string='Comision (%)', default=0.0)
    fee_fixed_amount = fields.Monetary(string='Comision fija', currency_field='currency_id', default=0.0)
    fee_tax_percent = fields.Float(string='IVA comision (%)', default=0.0)
    withholding_percent = fields.Float(string='Retencion/Percepcion (%)', default=0.0)

    def map_card_values(self):
        self.ensure_one()
        return {
            'name': self.name,
            'id': self.id,
            'installments': [],
        }

    def _prs_as_config_dict(self):
        """Configuracion de la tarjeta en el formato usado por PRS.
        Fallback: tarjeta → procesador."""
        self.ensure_one()
        p = self.provider_id
        return {
            'merchant_number': self.merchant_number or '',
            'delay_days': self.settlement_delay_days or p.settlement_delay_days or 0,
            'day_type': self.settlement_day_type or p.settlement_day_type or 'calendar',
            'journal': self.settlement_journal_id or p.settlement_journal_id,
            'fee_percent': self.fee_percent or p.fee_percent or 0.0,
            'fee_fixed_amount': self.fee_fixed_amount or p.fee_fixed_amount or 0.0,
            'fee_tax_percent': self.fee_tax_percent or p.fee_tax_percent or 0.0,
            'withholding_percent': self.withholding_percent or p.withholding_percent or 0.0,
        }


class AccountCardInstallment(models.Model):
    """Plan de cuotas de una tarjeta.
    Incluye el modelo base de card_installment (ADHOC SA) extendido con campos de PRS.
    Los campos PRS del plan tienen precedencia sobre los de la tarjeta padre."""
    _name = 'account.card.installment'
    _description = 'Installment Plan'

    card_id = fields.Many2one('account.card', string='Tarjeta', required=True)
    name = fields.Char('Nombre del plan', default='/', help='Nombre informativo del plan a mostrar')
    divisor = fields.Integer(help='Numero de cuotas en que se divide el total')
    installment = fields.Integer(
        string='Plan gateway',
        help='ID del plan a informar al gateway de pago electronico',
    )
    surcharge_coefficient = fields.Float(
        default=1.0,
        digits='Installment coefficient',
        help='Factor sobre el total para calcular el cargo financiero. '
             'Ejemplo: 1.06 para un recargo del 6%.',
    )
    bank_discount = fields.Float(
        help='Porcentaje de reintegro que acuerda el comercio con el banco o marca de tarjeta',
    )
    active = fields.Boolean(default=True)

    # Campos PRS — sobreescriben los de la tarjeta padre cuando estan definidos
    merchant_number = fields.Char(
        string='Numero de comercio',
        help='Deja vacio para heredar el numero de la tarjeta.',
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
        domain="[('type', '=', 'bank')]",
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='card_id.company_id.currency_id',
        readonly=True,
    )
    fee_percent = fields.Float(string='Comision (%)', default=0.0)
    fee_fixed_amount = fields.Monetary(string='Comision fija', currency_field='currency_id', default=0.0)
    fee_tax_percent = fields.Float(string='IVA comision (%)', default=0.0)
    withholding_percent = fields.Float(string='Retencion/Percepcion (%)', default=0.0)
    apply_commission_surcharge = fields.Boolean(
        string='Aplicar recargo comisiones',
        help='Si esta activo, se traslada al cliente el calculo de comision/IVA/retenciones del plan.',
    )

    @api.depends('card_id', 'card_id.name', 'name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = '%s (%s)' % (record.name, record.card_id.name)

    @api.constrains('divisor')
    def _check_divisor(self):
        for record in self:
            if record.divisor < 0:
                raise ValidationError(_('El numero de cuotas no puede ser negativo.'))

    # ── Métodos de card_installment ───────────────────────────────────────────

    def get_fees(self, amount):
        self.ensure_one()
        return amount * self.surcharge_coefficient - amount

    def get_real_total(self, amount):
        self.ensure_one()
        return amount * self.surcharge_coefficient

    def card_installment_tree(self, amount_total):
        tree = {}
        for card in self.mapped('card_id'):
            tree[card.id] = card.map_card_values()
        for installment in self:
            tree[installment.card_id.id]['installments'].append(
                installment.map_installment_values(amount_total)
            )
        return tree

    def map_installment_values(self, amount_total):
        self.ensure_one()
        amount = amount_total * self.surcharge_coefficient
        installment_amount = amount / self.divisor if self.divisor > 0 else 0.0
        return {
            'id': self.id,
            'name': self.name,
            'installment': self.installment,
            'coefficient': self.surcharge_coefficient,
            'bank_discount': self.bank_discount,
            'divisor': self.divisor,
            'base_amount': amount_total,
            'amount': amount,
            'fee': amount - amount_total,
            'description': _('%s cuota/s de %.2f (total %.2f)') % (
                self.divisor, installment_amount, amount
            ),
        }

    # ── Método PRS ────────────────────────────────────────────────────────────

    def _prs_as_config_dict(self):
        """Config dict con fallback: plan → tarjeta → procesador."""
        self.ensure_one()
        card = self.card_id
        p = card.provider_id
        coef = self.surcharge_coefficient if self.surcharge_coefficient and self.surcharge_coefficient > 0 else 1.0
        return {
            'merchant_number': self.merchant_number or card.merchant_number or '',
            'delay_days': self.settlement_delay_days or card.settlement_delay_days or p.settlement_delay_days or 0,
            'day_type': self.settlement_day_type or card.settlement_day_type or p.settlement_day_type or 'calendar',
            'journal': self.settlement_journal_id or card.settlement_journal_id or p.settlement_journal_id,
            'fee_percent': self.fee_percent or card.fee_percent or p.fee_percent or 0.0,
            'fee_fixed_amount': self.fee_fixed_amount or card.fee_fixed_amount or p.fee_fixed_amount or 0.0,
            'fee_tax_percent': self.fee_tax_percent or card.fee_tax_percent or p.fee_tax_percent or 0.0,
            'withholding_percent': self.withholding_percent or card.withholding_percent or p.withholding_percent or 0.0,
            'surcharge_coefficient': coef,
            'bank_discount': self.bank_discount or 0.0,
            'apply_commission_surcharge': bool(self.apply_commission_surcharge),
        }
