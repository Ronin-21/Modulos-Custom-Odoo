import re
from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Campo técnico para poder ocultar/mostrar la UI según el ajuste global.
    volume_discount_enabled = fields.Boolean(
        string="Descuento por Volumen Habilitado",
        compute="_compute_volume_discount_enabled",
    )

    # Total de litros (Float para soportar decimales)
    x_total_units = fields.Float(
        string="Total de Litros",
        compute="_compute_total_units",
        store=True,
        digits=(10, 2),
    )

    # Descuento automático (%), según reglas
    discount_global = fields.Float(
        string="Descuento por Volumen (%)",
        compute="_compute_discount_global",
        store=True,  # ← AGREGAR store=True
    )

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------
    def _is_volume_discount_enabled(self):
        param = self.env["ir.config_parameter"].sudo().get_param(
            "sales_total_units.enable_volume_discount", default="False"
        )
        return str(param).lower() in ("1", "true", "yes", "y", "on")

    def _compute_volume_discount_enabled(self):
        enabled = self._is_volume_discount_enabled()
        for order in self:
            order.volume_discount_enabled = enabled

    def _parse_uom_name_to_liters(self, qty, name):
        """Fallback por nombre cuando la UoM está mal configurada."""
        if not qty or not name:
            return None

        txt = (name or "").strip().lower()

        def to_float(s):
            return float(s.replace(",", "."))

        # Ej: "500 ml", "500ml"
        m = re.search(r"(\d+(?:[\.,]\d+)?)\s*ml\b", txt)
        if m:
            ml = to_float(m.group(1))
            return qty * (ml / 1000.0)

        # Ej: "500 cc"
        m = re.search(r"(\d+(?:[\.,]\d+)?)\s*cc\b", txt)
        if m:
            cc = to_float(m.group(1))
            return qty * (cc / 1000.0)

        # Ej: "0.5 L", "1l"
        m = re.search(r"(\d+(?:[\.,]\d+)?)\s*l\b", txt)
        if m:
            lts = to_float(m.group(1))
            return qty * lts

        # Ej: "0,5 litro", "2 litros"
        m = re.search(r"(\d+(?:[\.,]\d+)?)\s*lit", txt)
        if m:
            lts = to_float(m.group(1))
            return qty * lts

        return None

    def _qty_to_liters(self, qty, uom, litro_uom):
        """Convierte qty en la UoM de la línea a litros."""
        if not qty or not uom:
            return 0.0

        liters_conv = 0.0
        if litro_uom and uom.category_id == litro_uom.category_id:
            try:
                liters_conv = uom._compute_quantity(qty, litro_uom)
            except Exception:
                liters_conv = 0.0

        liters_parsed = self._parse_uom_name_to_liters(qty, getattr(uom, "name", None))
        if liters_parsed is None:
            return liters_conv or 0.0

        if not liters_conv:
            return liters_parsed

        # Diferencia relativa > 20% => UoM mal configurada
        if abs(liters_conv - liters_parsed) / max(liters_parsed, 1e-9) > 0.20:
            return liters_parsed

        return liters_conv

    # ------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------
    @api.depends(
        "order_line.product_uom_qty",
        "order_line.product_uom",
        "order_line.product_uom.name",
        "order_line.display_type",
    )
    def _compute_total_units(self):
        litro_uom = self.env.ref("uom.product_uom_litre", raise_if_not_found=False)
        for order in self:
            total = 0.0
            for line in order.order_line:
                if line.display_type:
                    continue
                total += order._qty_to_liters(line.product_uom_qty, line.product_uom, litro_uom)
            order.x_total_units = total

    @api.depends("x_total_units")
    def _compute_discount_global(self):
        enabled = self._is_volume_discount_enabled()
        
        for order in self:
            if not enabled:
                order.discount_global = 0.0
                continue

            litros = order.x_total_units or 0.0
            rules = self.env["discount.rule"].search([], order="min_liters asc")
            applicable = None
            for r in rules:
                if litros >= (r.min_liters or 0.0):
                    applicable = r
            
            new_discount = applicable.discount if applicable else 0.0
            
            # Solo actualizar si cambió
            if order.discount_global != new_discount:
                order.discount_global = new_discount
                # Aplicar a las líneas
                self._apply_discount_to_lines(order, new_discount)

    def _apply_discount_to_lines(self, order, discount):
        """Aplicar descuento solo a líneas sin descuento manual."""
        for line in order.order_line:
            if line.display_type:
                continue
            # Opción A: no pisar si el usuario ya puso descuento manual
            if (line.discount or 0.0) == 0.0:
                line.discount = discount

    # ------------------------------------------------------------
    # Onchange (para UI en tiempo real)
    # ------------------------------------------------------------
    @api.onchange(
        "order_line",
        "order_line.product_uom_qty",
        "order_line.product_uom",
        "order_line.product_uom.name",
    )
    def _onchange_volume_discount_apply(self):
        """Aplicar el descuento automáticamente en la UI (sin romper manuales)."""
        enabled = self._is_volume_discount_enabled()
        if not enabled:
            return  # CLAVE: no tocar descuentos manuales si el check está apagado

        for order in self:
            disc = order.discount_global or 0.0
            for line in order.order_line:
                if line.display_type:
                    continue
                # Opción A: solo si no hay descuento manual
                if (line.discount or 0.0) == 0.0:
                    line.discount = disc