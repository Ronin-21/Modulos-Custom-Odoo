from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # Campo de trazabilidad: guarda la lista de precios individual usada en la línea de venta.
    # No se muestra en vistas ni en reportes PDF; es solo para consulta interna/auditoría.
    sale_line_pricelist_id = fields.Many2one(
        comodel_name='product.pricelist',
        string='Lista de Precio de Línea de Venta',
        readonly=True,
        copy=True,
        help='Lista de precios individual que se usó en la línea de venta de origen.',
    )
