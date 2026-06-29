from odoo import fields, models


class SaleAdvancePaymentCheck(models.TransientModel):
    _name = 'sale.advance.payment.check'
    _description = 'Cheque de Pago Adelantado'

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
    name = fields.Char(
        string='Número',
        required=True,
    )
    bank_id = fields.Many2one(
        'res.bank',
        string='Banco',
    )
    issuer_vat = fields.Char(string='CUIT del Emisor')
    payment_date = fields.Date(
        string='Fecha de Pago',
        required=True,
        default=fields.Date.today,
    )
    amount = fields.Monetary(
        string='Importe',
        currency_field='currency_id',
        required=True,
    )
