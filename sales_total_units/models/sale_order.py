from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Total de litros
    x_total_units = fields.Integer(
        string="Total de Litros",
        compute="_compute_total_units",
        store=True,
    )

    # Descuento global automático (%)
    discount_global = fields.Float(
        string="Descuento Global (%)",
        compute="_compute_discount_global",
        store=True,
    )

    @api.depends("order_line.product_uom_qty", "order_line.product_uom")
    def _compute_total_units(self):
        litro_uom = self.env.ref("uom.product_uom_litre", raise_if_not_found=False)
        for order in self:
            litros_total = 0
            for line in order.order_line:
                if litro_uom and line.product_uom.category_id == litro_uom.category_id:
                    qty_in_litros = line.product_uom._compute_quantity(
                        line.product_uom_qty, litro_uom
                    )
                    if qty_in_litros.is_integer():
                        litros_total += int(qty_in_litros)
            order.x_total_units = litros_total

    @api.depends("x_total_units")
    def _compute_discount_global(self):
        for order in self:
            litros = order.x_total_units
            # Buscar la regla más alta aplicable
            rules = self.env['discount.rule'].search([], order='min_liters asc')
            applicable = rules.filtered(lambda r: litros >= r.min_liters)
            if applicable:
                order.discount_global = applicable[-1].discount
            else:
                order.discount_global = 0

    # Aplicar descuento global en cada línea
    @api.onchange("discount_global", "order_line.product_uom_qty")
    def _apply_discount_global(self):
        for order in self:
            for line in order.order_line:
                line.discount = order.discount_global
