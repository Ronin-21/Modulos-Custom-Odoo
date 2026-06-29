# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SaleCashierSessionLine(models.Model):
    _name = 'sale.cashier.session.line'
    _description = 'Línea de Rendición de Sesión de Caja'
    _order = 'sequence, id'

    session_id = fields.Many2one('sale.cashier.session', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one('res.currency', related='session_id.currency_id', store=True, readonly=True)
    payment_journal_id = fields.Many2one('account.journal', string='Medio de pago', required=False)
    sequence = fields.Integer(default=10)
    amount_expected = fields.Monetary(string='Esperado (sistema)', currency_field='currency_id')
    amount_real = fields.Monetary(string='Rendido (real)', default=0.0, currency_field='currency_id')
    difference = fields.Monetary(string='Diferencia', compute='_compute_difference', store=True, currency_field='currency_id')
    notes = fields.Char(string='Observaciones')

    @api.depends('amount_real', 'amount_expected')
    def _compute_difference(self):
        for line in self:
            line.difference = line.amount_real - line.amount_expected
