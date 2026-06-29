# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleCashierPaymentLine(models.TransientModel):
    _inherit = 'sale.cashier.payment.line'

    prs_card_provider_id = fields.Many2one(
        'prs.card.provider',
        compute='_compute_prs_card_provider_id',
        store=False,
        string='Procesador',
    )

    @api.depends('payment_journal_id')
    def _compute_prs_card_provider_id(self):
        for line in self:
            # sudo() necesario: el journal puede pertenecer a la empresa padre
            # (ej. Tarjetas en DEP. PRINCIPAL usado desde una sucursal).
            journal = line.payment_journal_id.sudo()
            line.prs_card_provider_id = getattr(journal, 'prs_card_provider_id', False)
    prs_card_id = fields.Many2one(
        'account.card',
        string='Tarjeta',
        domain="[('provider_id', '=', prs_card_provider_id), ('active', '=', True)]",
    )
    prs_installment_id = fields.Many2one(
        'account.card.installment',
        string='Plan de cuotas',
        domain="[('card_id', '=', prs_card_id), ('active', '=', True)]",
    )
    amount_base = fields.Monetary(
        string='Monto base',
        currency_field='currency_id',
    )

    @api.onchange('financing_plan_id')
    def _onchange_financing_plan(self):
        super()._onchange_financing_plan()
        self.prs_card_id = False
        self.prs_installment_id = False

    @api.onchange('payment_journal_id')
    def _onchange_payment_journal(self):
        super()._onchange_payment_journal()
        self.prs_card_id = False
        self.prs_installment_id = False

    @api.onchange('prs_card_id')
    def _onchange_prs_card_id_sof(self):
        self.prs_installment_id = False

    @api.onchange('prs_installment_id')
    def _onchange_prs_installment_sof(self):
        installment = self.prs_installment_id
        if not installment:
            return
        coef = installment._sof_effective_coefficient()
        if coef <= 1.0:
            return
        # Leer payment_mode desde el wizard (la BD) para evitar el related no almacenado
        # que no está disponible en el contexto de onchange de línea one2many.
        wizard = self.wizard_id
        if wizard and wizard.payment_mode == 'multi':
            # En multi, el amount actual es el monto base ingresado por el usuario.
            current = self.amount or 0.0
            if current > 0:
                self.amount_base = current
                self.amount = round(current * coef, 2)
                self.cash_received = self.amount
        else:
            total = self.order_amount_total or 0.0
            base_untaxed = self.order_amount_untaxed or 0.0
            self.amount_base = total
            self.amount = round(total + base_untaxed * (coef - 1.0), 2)
            self.cash_received = self.amount

    @api.onchange('amount_base')
    def _onchange_amount_base(self):
        """Al ingresar el monto base, calcula el A cobrar aplicando el recargo del plan de cuotas."""
        installment = self.prs_installment_id
        coef = installment._sof_effective_coefficient() if installment else 1.0
        base = self.amount_base or 0.0
        if base <= 0:
            return
        wizard = self.wizard_id
        if wizard and wizard.payment_mode != 'multi':
            # Modo único: el recargo aplica solo al neto (mismo criterio que _apply_card_installment_adjustment).
            # Usar order_amount_untaxed para evitar que el IVA sea parte del cálculo del recargo.
            base_untaxed = self.order_amount_untaxed or 0.0
            self.amount = round(base + base_untaxed * (coef - 1.0), 2)
        else:
            self.amount = round(base * coef, 2)
        self.cash_received = self.amount

    @api.onchange('amount')
    def _onchange_amount_reverse_base(self):
        """Al modificar el A cobrar directamente, recalcula el monto base."""
        installment = self.prs_installment_id
        if not installment:
            return
        coef = installment._sof_effective_coefficient()
        if coef <= 1.0:
            return
        amt = self.amount or 0.0
        self.amount_base = round(amt / coef, 2) if amt > 0 else 0.0
        self.cash_received = amt
