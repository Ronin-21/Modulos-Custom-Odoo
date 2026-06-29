# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class PrsMoneyFlow(models.Model):
    _inherit = 'prs.money.flow'

    flow_type = fields.Selection(
        selection_add=[('card_settlement', 'Liquidacion de tarjeta')],
        ondelete={'card_settlement': 'set default'},
    )


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    prs_card_provider_id = fields.Many2one(
        'prs.card.provider',
        related='journal_id.prs_card_provider_id',
        string='Procesador de tarjetas',
        store=False,
    )
    prs_card_id = fields.Many2one(
        'account.card',
        string='Tarjeta',
        domain="[('provider_id', '=', prs_card_provider_id)]",
        ondelete='set null',
        copy=False,
    )
    prs_installment_id = fields.Many2one(
        'account.card.installment',
        string='Plan de cuotas',
        domain="[('card_id', '=', prs_card_id), ('active', '=', True)]",
        ondelete='set null',
        copy=False,
    )

    @api.onchange('journal_id')
    def _onchange_journal_prs_card_payment(self):
        self.prs_card_id = False
        self.prs_installment_id = False

    @api.onchange('prs_card_id')
    def _onchange_prs_card_id_payment(self):
        self.prs_installment_id = False

    def _prs_card_settlement_date(self, base_date, delay_days, day_type):
        if not delay_days:
            return base_date
        if day_type == 'business':
            current = base_date
            remaining = delay_days
            while remaining > 0:
                current += timedelta(days=1)
                if current.weekday() < 5:
                    remaining -= 1
            return current
        return base_date + timedelta(days=delay_days)

    def _prs_get_money_flow_entries(self):
        self.ensure_one()
        entries = super()._prs_get_money_flow_entries()

        if not self.prs_card_id or not self.company_id.prs_money_flow_enabled:
            return entries

        installment = self.prs_installment_id
        config = installment._prs_as_config_dict() if installment else self.prs_card_id._prs_as_config_dict()

        settlement_journal = config.get('journal')
        if not settlement_journal:
            return entries

        delay_days = config.get('delay_days', 0)
        day_type = config.get('day_type', 'calendar')
        fee_percent = config.get('fee_percent', 0.0)
        fee_tax_percent = config.get('fee_tax_percent', 0.0)
        withholding_percent = config.get('withholding_percent', 0.0)
        fee_fixed = config.get('fee_fixed_amount', 0.0)
        surcharge_coefficient = config.get('surcharge_coefficient', 1.0) or 1.0
        bank_discount = config.get('bank_discount', 0.0) or 0.0

        base_date = self.date or fields.Date.context_today(self)
        expected_date = self._prs_card_settlement_date(base_date, delay_days, day_type)

        # El settlement usa el monto del pago Odoo como gross (== lo que entró al diario puente).
        # surcharge_coefficient solo afecta el label (cuotas de $X); si el recargo ya está
        # en la factura el coeficiente llega en 1.0 y no hay diferencia.
        amount_gross = abs(self.amount)
        fee_amount = round(amount_gross * fee_percent / 100.0, 2) + fee_fixed
        fee_tax_amount = round(fee_amount * fee_tax_percent / 100.0, 2)
        withholding_amount = round(amount_gross * withholding_percent / 100.0, 2)
        # Reintegro del banco: reduce la comisión efectiva
        bank_discount_amount = round(amount_gross * bank_discount / 100.0, 2)
        net_fee = max(0.0, fee_amount - bank_discount_amount)

        card_name = self.prs_card_id.name
        plan_name = installment.name if installment else ''
        divisor = installment.divisor if installment else 0
        direction = 'inbound' if self.payment_type == 'inbound' else 'outbound'

        # Label: incluye cuotas y total con recargo cuando aplica
        if plan_name and divisor and surcharge_coefficient != 1.0:
            cuota_amount = round(amount_gross * surcharge_coefficient / divisor, 2)
            label = '%s / %s — %d cuotas de $%.2f' % (card_name, plan_name, divisor, cuota_amount)
        elif plan_name:
            label = '%s / %s' % (card_name, plan_name)
        else:
            label = card_name

        settlement_vals = self._prs_prepare_money_flow_vals(
            journal=settlement_journal,
            expected_date=expected_date,
            amount=amount_gross,
            direction=direction,
            label=label,
            flow_type='card_settlement',
            unique_suffix='card_settlement',
            extra={
                'fee_amount': net_fee,
                'fee_tax_amount': fee_tax_amount,
                'withholding_amount': withholding_amount,
                'card_label': card_name,
                'plan_label': plan_name,
                'payment_method_label': card_name,
                # Si el diario destino tiene control manual de acreditaciones,
                # el cron no debe procesarlo: el wizard es el único camino.
                'auto_create_statement': not settlement_journal.prs_accreditation_control,
            },
        )
        # El extracto del diario puente (Tarjetas Clover) se crea durante la acreditación
        # como src_line. Suprimir la creación automática del flujo base para evitar un
        # BNK redundante que no puede reconciliarse correctamente mediante wash trade.
        entries_no_auto = [{**e, 'auto_create_statement': False} for e in entries]
        return entries_no_auto + [settlement_vals]
