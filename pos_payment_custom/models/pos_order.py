from odoo import models, fields

class PosOrder(models.Model):
    _inherit = 'pos.order'

    # Campo para guardar el ajuste aplicado
    adjustment_type = fields.Selection(
        [
            ('discount', 'Descuento'),
            ('surcharge', 'Recargo'),
            ('none', 'Ninguno')
        ],
        string="Tipo de ajuste",
        default='none',
        readonly=True
    )
    adjustment_amount = fields.Float(
        string="Monto de ajuste",
        readonly=True,
        help="Monto del descuento o recargo aplicado"
    )
    adjustment_percent = fields.Float(
        string="Porcentaje de ajuste",
        readonly=True
    )