from odoo import models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    """Sale Order - Validación de Stock Negativo"""
    _inherit = 'sale.order'

    def _validate_stock_availability(self):
        """Valida que haya stock disponible para los productos de la venta"""
        productos_sin_stock = []

        for line in self.order_line:
            if line.product_id.type == 'service':
                continue

            stock_disponible = line.product_id.qty_available
            stock_pronosticado = line.product_id.virtual_available - line.product_id.qty_available
            cantidad_solicitada = line.product_uom_qty

            if stock_disponible < cantidad_solicitada:
                productos_sin_stock.append({
                    'nombre': line.product_id.name,
                    'stock': stock_disponible,
                    'pronosticado': max(0, stock_pronosticado),
                    'solicitado': cantidad_solicitada
                })

        if productos_sin_stock:
            mensaje = "⚠️ STOCK INSUFICIENTE\n\n"
            mensaje += "Los siguientes productos no tienen stock disponible:\n\n"
            for prod in productos_sin_stock:
                mensaje += f"• {prod['nombre']}\n"
                mensaje += f"  Stock disponible: {prod['stock']}"
                if prod['pronosticado'] > 0:
                    mensaje += f" | Pronosticado: {prod['pronosticado']}"
                mensaje += f" | Cantidad solicitada: {prod['solicitado']}\n\n"
            mensaje += "Por favor, verifique el inventario antes de continuar."
            raise UserError(mensaje)

    def action_confirm(self):
        """Valida stock antes de confirmar la venta"""
        self.ensure_one()
        self._validate_stock_availability()
        return super(SaleOrder, self).action_confirm()