from odoo import api, fields, models

# Códigos de métodos de pago de cheques (l10n_latam_check).
_CHECK_PAYMENT_METHOD_CODES = frozenset({
    'new_third_party_checks',
    'in_third_party_checks',
    'out_third_party_checks',
    'return_third_party_checks',
    'own_checks',
})


class SaleAdvancePaymentLine(models.TransientModel):
    _name = 'sale.advance.payment.line'
    _description = 'Línea de Pago Adelantado (múltiples métodos)'

    wizard_id = fields.Many2one(
        'sale.advance.payment.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        related='wizard_id.company_id',
        string='Empresa',
        readonly=True,
    )
    currency_id = fields.Many2one(
        related='wizard_id.currency_id',
        string='Moneda',
        readonly=True,
    )
    allowed_journal_ids = fields.Many2many(
        related='wizard_id.allowed_journal_ids',
        string='Diarios Permitidos',
        readonly=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario',
        required=True,
        domain="[('id', 'in', allowed_journal_ids)]",
    )
    payment_method_line_id = fields.Many2one(
        'account.payment.method.line',
        string='Método de Pago',
        domain="[('journal_id', '=', journal_id), ('payment_type', '=', 'inbound')]",
    )
    amount = fields.Monetary(
        string='Importe',
        currency_field='currency_id',
    )
    communication = fields.Char(string='Referencia')
    is_check = fields.Boolean(
        string='Es cheque',
        compute='_compute_is_check',
    )

    @api.depends('payment_method_line_id', 'payment_method_line_id.code')
    def _compute_is_check(self):
        for line in self:
            code = line.payment_method_line_id.code or ''
            line.is_check = code in _CHECK_PAYMENT_METHOD_CODES

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        self.payment_method_line_id = False
        if self.journal_id:
            available = self.journal_id._get_available_payment_method_lines('inbound')
            non_check = available.filtered(lambda m: m.code not in _CHECK_PAYMENT_METHOD_CODES)
            self.payment_method_line_id = non_check[:1] or available[:1]
