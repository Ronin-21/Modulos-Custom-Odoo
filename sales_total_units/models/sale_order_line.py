import re

from odoo import models, fields, api


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # Litros de esta línea específica
    line_total_units = fields.Float(
        string="Litros de la Línea",
        compute="_compute_line_total_units",
        store=True,
        help="Total de litros de esta línea de pedido",
    )

    def _parse_uom_name_to_liters(self, qty, name):
        if not qty or not name:
            return None

        txt = (name or "").strip().lower()

        def to_float(s):
            return float(s.replace(",", "."))

        m = re.search(r"(\d+(?:[\.,]\d+)?)\s*ml\b", txt)
        if m:
            ml = to_float(m.group(1))
            return qty * (ml / 1000.0)

        m = re.search(r"(\d+(?:[\.,]\d+)?)\s*cc\b", txt)
        if m:
            cc = to_float(m.group(1))
            return qty * (cc / 1000.0)

        m = re.search(r"(\d+(?:[\.,]\d+)?)\s*l\b", txt)
        if m:
            lts = to_float(m.group(1))
            return qty * lts

        m = re.search(r"(\d+(?:[\.,]\d+)?)\s*lit", txt)
        if m:
            lts = to_float(m.group(1))
            return qty * lts

        return None

    @api.depends("product_uom_qty", "product_uom", "product_uom.name", "display_type")
    def _compute_line_total_units(self):
        litro_uom = self.env.ref("uom.product_uom_litre", raise_if_not_found=False)
        for line in self:
            if line.display_type:
                line.line_total_units = 0.0
                continue

            qty = line.product_uom_qty
            uom = line.product_uom

            liters_conv = 0.0
            if qty and uom and litro_uom and uom.category_id == litro_uom.category_id:
                try:
                    liters_conv = uom._compute_quantity(qty, litro_uom)
                except Exception:
                    liters_conv = 0.0

            liters_parsed = line._parse_uom_name_to_liters(qty, getattr(uom, "name", None))
            if liters_parsed is None:
                line.line_total_units = liters_conv or 0.0
                continue

            if not liters_conv:
                line.line_total_units = liters_parsed
                continue

            if abs(liters_conv - liters_parsed) / max(liters_parsed, 1e-9) > 0.20:
                line.line_total_units = liters_parsed
            else:
                line.line_total_units = liters_conv
