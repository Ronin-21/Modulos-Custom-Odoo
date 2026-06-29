# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    prs_card_provider_id = fields.Many2one(
        'prs.card.provider',
        related='journal_id.prs_card_provider_id',
        string='Procesador',
    )
    prs_card_id = fields.Many2one(
        'account.card',
        string='Tarjeta',
        domain="[('provider_id', '=', prs_card_provider_id)]",
        ondelete='set null',
    )
    prs_installment_id = fields.Many2one(
        'account.card.installment',
        string='Plan de cuotas',
        domain="[('card_id', '=', prs_card_id), ('active', '=', True)]",
        ondelete='set null',
    )

    @api.onchange('journal_id')
    def _onchange_journal_prs_card(self):
        self.prs_card_id = False
        self.prs_installment_id = False

    @api.onchange('prs_card_id')
    def _onchange_prs_card_id(self):
        self.prs_installment_id = False

    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)
        if self.prs_card_id:
            vals['prs_card_id'] = self.prs_card_id.id
        if self.prs_installment_id:
            vals['prs_installment_id'] = self.prs_installment_id.id
        return vals
