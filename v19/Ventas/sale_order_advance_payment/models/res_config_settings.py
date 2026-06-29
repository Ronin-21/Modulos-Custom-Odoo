from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sale_advance_payment_journal_ids = fields.Many2many(
        related='company_id.sale_advance_payment_journal_ids',
        string='Diarios de Pago Aceptados',
        readonly=False,
    )
    sale_advance_payment_default_journal_id = fields.Many2one(
        related='company_id.sale_advance_payment_default_journal_id',
        string='Diario por Defecto',
        readonly=False,
    )
    sale_advance_payment_default_mode = fields.Selection(
        related='company_id.sale_advance_payment_default_mode',
        string='Modo de Cobro por Defecto',
        readonly=False,
    )
    sale_advance_payment_allow_multiple = fields.Boolean(
        related='company_id.sale_advance_payment_allow_multiple',
        string='Permitir Múltiples Anticipos por Orden',
        readonly=False,
    )
    sale_advance_payment_require_reference = fields.Boolean(
        related='company_id.sale_advance_payment_require_reference',
        string='Requerir Referencia',
        readonly=False,
    )
