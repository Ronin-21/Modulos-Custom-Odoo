from odoo import models, fields


class PosOrder(models.Model):
    _inherit = "pos.order"

    adjustment_type = fields.Selection(
        [
            ("discount", "Descuento"),
            ("surcharge", "Recargo"),
            ("none", "Ninguno"),
        ],
        string="Tipo de ajuste",
        default="none",
        readonly=True,
    )
    adjustment_amount = fields.Float(
        string="Monto de ajuste",
        readonly=True,
        help="Monto del descuento o recargo aplicado",
    )
    adjustment_percent = fields.Float(
        string="Porcentaje de ajuste",
        readonly=True,
    )

    def _order_fields(self, ui_order):
        res = super()._order_fields(ui_order)
        res.update(
            {
                "adjustment_type": ui_order.get("adjustment_type", "none") or "none",
                "adjustment_amount": ui_order.get("adjustment_amount", 0.0) or 0.0,
                "adjustment_percent": ui_order.get("adjustment_percent", 0.0) or 0.0,
            }
        )
        return res
