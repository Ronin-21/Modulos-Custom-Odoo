from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    sale_advance_payment_journal_ids = fields.Many2many(
        'account.journal',
        'res_company_sale_advance_journal_rel',
        'company_id',
        'journal_id',
        string='Diarios de Pago Aceptados',
        domain="[('type', 'in', ['bank', 'cash'])]",
        help='Diarios habilitados para registrar pagos adelantados. '
             'Si se deja vacío, se aceptan todos los diarios de banco/efectivo.',
    )
    sale_advance_payment_default_journal_id = fields.Many2one(
        'account.journal',
        string='Diario por Defecto',
        domain="[('type', 'in', ['bank', 'cash'])]",
        help='Diario preseleccionado al abrir el wizard de pago adelantado.',
    )
    sale_advance_payment_default_mode = fields.Selection(
        selection=[
            ('single', 'Pago único'),
            ('multi', 'Múltiples métodos'),
        ],
        string='Modo de Cobro por Defecto',
        default='single',
    )
    sale_advance_payment_allow_multiple = fields.Boolean(
        string='Permitir Múltiples Anticipos por Orden',
        default=False,
        help='Si está activo, una Orden de Venta puede tener más de un pago adelantado.',
    )
    sale_advance_payment_require_reference = fields.Boolean(
        string='Requerir Referencia',
        default=False,
        help='Si está activo, el campo Referencia es obligatorio al registrar el pago.',
    )
