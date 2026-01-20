from odoo import models, fields, api

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # Litros de esta línea específica
    line_total_units = fields.Float(
        string="Litros de la Línea",
        compute="_compute_line_total_units",
        store=True,
        help="Total de litros de esta línea de pedido"
    )

    @api.depends("product_uom_qty", "product_uom")
    def _compute_line_total_units(self):
        litro_uom = self.env.ref("uom.product_uom_litre", raise_if_not_found=False)
        for line in self:
            if litro_uom and line.product_uom.category_id == litro_uom.category_id:
                qty_in_litros = line.product_uom._compute_quantity(
                    line.product_uom_qty, litro_uom
                )
                line.line_total_units = qty_in_litros
            else:
                line.line_total_units = 0