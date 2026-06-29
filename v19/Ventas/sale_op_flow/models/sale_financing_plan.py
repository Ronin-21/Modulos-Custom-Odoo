# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SaleFinancingPlan(models.Model):
    _name = 'sale.financing.plan'
    _description = 'Plan de Pago / Financiación'
    _order = 'sequence, name'
    _rec_name = 'name'

    name = fields.Char(string='Nombre del plan', required=True, default='Plan sin nombre')
    payment_journal_id = fields.Many2one(
        'account.journal', string='Diario / Medio de pago',
        domain="[('type', 'in', ['bank', 'cash'])]",
    )
    card_name = fields.Char(string='Tarjeta / Red')
    installments = fields.Integer(string='Cuotas', default=1, required=True)
    adjustment_type = fields.Selection(
        [('none', 'Sin ajuste'), ('discount', 'Descuento'), ('surcharge', 'Recargo')],
        string='Tipo de ajuste', default='none', required=True,
    )
    adjustment_rate = fields.Float(string='Porcentaje (%)', default=0.0, digits=(5, 2))
    adjustment_product_id = fields.Many2one(
        'product.product', string='Producto de ajuste', domain=[('type', '=', 'service')],
    )
    requires_coupon = fields.Boolean(string='Requiere número de cupón (tarjeta)', default=False)
    requires_voucher = fields.Boolean(string='Requiere número de comprobante (transferencia)', default=False)
    is_pay_later = fields.Boolean(
        string='Cuenta Corriente (pago diferido)',
        help='Al usar este método, no se crea un pago inmediato. '
             'La factura queda pendiente con el término de pago indicado y '
             'el pedido puede despacharse igualmente.',
    )
    payment_term_id = fields.Many2one(
        'account.payment.term', string='Término de pago',
        help='Plazo de vencimiento aplicado a la factura cuando se usa este plan (ej. 30 días).',
    )
    is_check_payment = fields.Boolean(
        string='Cheque de tercero',
        help='Al usar este plan, el cajero ingresa número, banco y fecha del cheque recibido. '
             'Se registra como cheque de tercero recibido (l10n_latam_check). '
             'El diario debe tener habilitado el método "Cheques de terceros recibidos".',
    )
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        'res.company', string='Empresa',
        default=lambda self: self.env.company, index=True,
        help='Dejar vacío para que el plan sea global y esté disponible en todas las empresas.',
    )
    notes = fields.Text(string='Notas internas')

    def _build_auto_name(self):
        """Genera un nombre sugerido basado en los campos del plan."""
        if self.is_pay_later:
            base = _('Cuenta Corriente')
            if self.payment_term_id:
                base = f'{base} · {self.payment_term_id.name}'
            return base
        if self.is_check_payment:
            base = _('Cheque')
            if self.payment_journal_id:
                base = f'{base} · {self.payment_journal_id.name}'
            return base
        parts = []
        if self.payment_journal_id:
            parts.append(self.payment_journal_id.name)
        if self.card_name:
            parts.append(self.card_name)
        if self.installments > 1:
            parts.append(f'{self.installments} cuotas')
        elif self.installments == 1 and self.card_name:
            parts.append('1 pago')
        if self.adjustment_type == 'discount' and self.adjustment_rate:
            parts.append(f'-{self.adjustment_rate:.1f}%')
        elif self.adjustment_type == 'surcharge' and self.adjustment_rate:
            parts.append(f'+{self.adjustment_rate:.1f}%')
        return ' · '.join(parts) if parts else _('Plan sin nombre')

    @api.onchange('payment_journal_id', 'card_name', 'installments', 'adjustment_type',
                  'adjustment_rate', 'is_pay_later', 'payment_term_id', 'is_check_payment')
    def _onchange_suggest_name(self):
        # Solo sugiere el nombre si todavía está vacío o en el valor por defecto
        if not self.name or self.name == _('Plan sin nombre'):
            self.name = self._build_auto_name()

    @api.onchange('adjustment_type')
    def _onchange_adjustment_type_cleanup(self):
        if self.adjustment_type == 'none':
            self.adjustment_rate = 0.0
            self.adjustment_product_id = False

    @api.constrains('adjustment_rate')
    def _check_adjustment_rate(self):
        for plan in self:
            if not (0.0 <= plan.adjustment_rate <= 100.0):
                raise ValidationError(_('El porcentaje debe estar entre 0 y 100.'))

    @api.constrains('installments')
    def _check_installments(self):
        for plan in self:
            if plan.installments < 1:
                raise ValidationError(_('Las cuotas deben ser al menos 1.'))

    @api.constrains('is_pay_later', 'is_check_payment')
    def _check_payment_type_exclusive(self):
        for plan in self:
            if plan.is_pay_later and plan.is_check_payment:
                raise ValidationError(
                    _('El plan "%s" no puede ser simultáneamente Cuenta Corriente y Cheque.') % plan.name
                )

    @api.constrains('adjustment_type', 'adjustment_rate', 'adjustment_product_id')
    def _check_adjustment_product(self):
        for plan in self:
            if (not plan.is_pay_later
                    and not plan.is_check_payment
                    and plan.adjustment_type != 'none'
                    and plan.adjustment_rate > 0.0
                    and not plan.adjustment_product_id):
                raise ValidationError(
                    _('El plan "%s" tiene ajuste configurado pero sin producto de ajuste.') % plan.name
                )
