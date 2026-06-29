# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SaleCashierPaymentLine(models.TransientModel):
    _name = 'sale.cashier.payment.line'
    _description = 'Línea de cobro multi-pago'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'sale.cashier.payment.wizard',
        required=True,
        ondelete='cascade',
        readonly=True,
    )
    sequence = fields.Integer(default=10)
    line_type = fields.Selection([
        ('cash', 'Efectivo'),
        ('bank', 'Banco / Transferencia'),
        ('check', 'Cheque'),
        ('cc', 'Cuenta Corriente'),
    ], string='Tipo de línea', required=True, default='bank')

    currency_id = fields.Many2one(
        'res.currency',
        related='wizard_id.currency_id',
        store=False,
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        related='wizard_id.company_id',
        store=False,
        readonly=True,
    )
    # Relacionados del wizard para poder calcular en el onchange
    order_amount_total = fields.Monetary(
        related='wizard_id.order_amount_total',
        currency_field='currency_id',
        store=False,
        readonly=True,
    )
    order_amount_untaxed = fields.Monetary(
        related='wizard_id.order_amount_untaxed',
        currency_field='currency_id',
        store=False,
        readonly=True,
    )
    payment_mode = fields.Selection(
        related='wizard_id.payment_mode',
        store=False,
        readonly=True,
    )

    payment_journal_id = fields.Many2one(
        'account.journal',
        string='Medio de pago',
        domain="[('type', 'in', ['bank', 'cash']), ('company_id', '=', company_id)]",
    )
    financing_plan_id = fields.Many2one(
        'sale.financing.plan',
        string='Plan de pago',
        domain="[('active', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    coupon_number = fields.Char(string='Nº Cupón')
    requires_coupon = fields.Boolean(compute='_compute_requires_coupon', readonly=True)
    voucher_number = fields.Char(string='Nº Comprobante')
    requires_voucher = fields.Boolean(compute='_compute_requires_voucher', readonly=True)
    amount = fields.Monetary(string='Importe', currency_field='currency_id')
    is_cash_journal = fields.Boolean(compute='_compute_is_cash_journal', store=False)
    cash_received = fields.Monetary(string='Recibido', currency_field='currency_id', default=0.0)
    cash_change = fields.Monetary(string='Vuelto', compute='_compute_cash_change', currency_field='currency_id')

    # Cheque de tercero
    is_check_payment = fields.Boolean(compute='_compute_is_check_payment', store=False)
    check_number = fields.Char(string='Nº Cheque')
    check_payment_date = fields.Date(string='Fecha cobro')
    check_bank_id = fields.Many2one('res.bank', string='Banco emisor')
    check_issuer_vat = fields.Char(string='CUIT emisor')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'amount' not in fields_list:
            return res
        wizard_id = self.env.context.get('default_wizard_id')
        wizard = self.env['sale.cashier.payment.wizard'].browse(wizard_id) if wizard_id else False
        if not (wizard and wizard.exists()):
            return res
        if wizard.payment_mode == 'multi':
            # Multi-pago: el cajero ingresa el monto de cada medio manualmente (empieza en 0).
            # No autocompletamos con el "restante": una línea recién agregada todavía no está
            # persistida en el registro transitorio, por lo que multi_remaining devolvería el
            # total completo y la nueva línea nacería con el total en vez del saldo pendiente.
            res['amount'] = 0.0
            res['cash_received'] = 0.0
        elif not (res.get('amount') or 0.0) > 0:
            # Pago único: autocompletar con el total a cobrar (ya incluye el redondeo configurado).
            amt = wizard.total_to_collect if wizard.total_to_collect > 0.01 else 0.0
            res['amount'] = amt
            res['cash_received'] = amt
        return res

    @api.depends('line_type')
    def _compute_is_cash_journal(self):
        for line in self:
            line.is_cash_journal = line.line_type == 'cash'

    @api.depends('line_type')
    def _compute_is_check_payment(self):
        for line in self:
            line.is_check_payment = line.line_type == 'check'

    @api.depends('cash_received', 'amount')
    def _compute_cash_change(self):
        for line in self:
            excess = (line.cash_received or 0.0) - (line.amount or 0.0)
            line.cash_change = excess if excess > 0.01 else 0.0

    @api.depends('financing_plan_id')
    def _compute_requires_coupon(self):
        for line in self:
            line.requires_coupon = bool(line.financing_plan_id and line.financing_plan_id.requires_coupon)

    @api.depends('financing_plan_id')
    def _compute_requires_voucher(self):
        for line in self:
            line.requires_voucher = bool(line.financing_plan_id and line.financing_plan_id.requires_voucher)

    @api.onchange('financing_plan_id')
    def _onchange_financing_plan(self):
        plan = self.financing_plan_id
        if plan and plan.payment_journal_id:
            self.payment_journal_id = plan.payment_journal_id

        # Limpiar datos de cheque al cambiar a un plan que no es cheque
        if not (plan and plan.is_check_payment):
            self.check_number = False
            self.check_payment_date = False
            self.check_bank_id = False
            self.check_issuer_vat = False
        else:
            # Auto-fill CUIT del emisor desde el partner del pedido (igual que nativo)
            partner = self.wizard_id.sale_order_id.partner_id if self.wizard_id else False
            if partner and partner.vat and not self.check_issuer_vat:
                self.check_issuer_vat = partner.vat

        mode = self.payment_mode or 'single'
        base = self.order_amount_untaxed or 0.0
        total = self.order_amount_total or 0.0

        if not plan or plan.adjustment_type == 'none' or not plan.adjustment_rate:
            if mode == 'single' and total > 0:
                # Usar total_to_collect del wizard que ya incluye el redondeo configurado
                amt = self.wizard_id.total_to_collect if self.wizard_id else total
                self.amount = amt if amt > 0 else total
                self.cash_received = self.amount
            return

        if mode == 'single':
            # Pago único: ajuste sobre la base imponible del pedido
            if plan.adjustment_type == 'discount':
                amt = round(total - (base * plan.adjustment_rate / 100.0), 2)
            else:
                amt = round(total + (base * plan.adjustment_rate / 100.0), 2)
            # Aplicar redondeo de efectivo si está configurado
            try:
                rid = int(self.env['ir.config_parameter'].sudo().get_param(
                    'sale_op_flow.cash_rounding_id', '0') or 0)
                if rid:
                    cr = self.env['account.cash.rounding'].browse(rid)
                    if cr.exists():
                        amt = cr.round(amt)
            except (ValueError, TypeError):
                pass
            self.amount = amt
            self.cash_received = self.amount
        else:
            # Múltiples pagos: ajuste sobre el monto de esta línea
            current = self.amount or 0.0
            if plan.adjustment_type == 'surcharge' and current > 0:
                self.amount = round(current * (1.0 + plan.adjustment_rate / 100.0), 2)
                self.cash_received = self.amount

    @api.onchange('amount')
    def _onchange_amount_apply_surcharge(self):
        """En modo multi, aplica el recargo del plan sobre el monto base ingresado."""
        # Leer payment_mode desde el wizard (la BD), no desde el related no almacenado,
        # ya que en onchange de línea de one2many el related puede no estar disponible.
        if not self.wizard_id or self.wizard_id.payment_mode != 'multi':
            return
        plan = self.financing_plan_id
        if not plan or plan.adjustment_type != 'surcharge' or not plan.adjustment_rate:
            return
        base = self.amount or 0.0
        if base <= 0:
            return
        new_amount = round(base * (1.0 + plan.adjustment_rate / 100.0), 2)
        if abs(new_amount - base) > 0.01:
            self.amount = new_amount
            self.cash_received = new_amount

    @api.onchange('payment_journal_id')
    def _onchange_payment_journal(self):
        if (
            self.financing_plan_id
            and self.payment_journal_id
            and self.financing_plan_id.payment_journal_id != self.payment_journal_id
        ):
            self.financing_plan_id = False
