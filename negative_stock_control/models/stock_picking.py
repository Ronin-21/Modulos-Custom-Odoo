from odoo import models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    """Stock Picking - Validación de Stock para Entregas"""
    _inherit = 'stock.picking'

    def _validate_stock_for_picking(self):
        """Valida stock disponible para órdenes de entrega"""
        if self.picking_type_id.code != 'outgoing':
            return
        
        productos_sin_stock = []

        for line in self.move_ids:
            if line.product_id.type == 'service':
                continue

            stock_disponible = line.product_id.qty_available
            cantidad_solicitada = line.product_uom_qty
            
            if stock_disponible < cantidad_solicitada:
                stock_pronosticado = line.product_id.virtual_available - line.product_id.qty_available
                productos_sin_stock.append({
                    'nombre': line.product_id.name,
                    'stock': stock_disponible,
                    'pronosticado': max(0, stock_pronosticado),
                    'solicitado': cantidad_solicitada
                })

        if productos_sin_stock:
            mensaje = "⚠️ STOCK INSUFICIENTE EN ORDEN DE ENTREGA\n\n"
            mensaje += "Los siguientes productos no tienen stock disponible:\n\n"
            for prod in productos_sin_stock:
                mensaje += f"• {prod['nombre']}\n"
                mensaje += f"  Stock disponible: {prod['stock']}"
                if prod['pronosticado'] > 0:
                    mensaje += f" | Pronosticado: {prod['pronosticado']}"
                mensaje += f" | Cantidad solicitada: {prod['solicitado']}\n\n"
            mensaje += "Por favor, verifique el inventario antes de continuar."
            raise UserError(mensaje)

    def button_validate(self):
        """Valida stock antes de confirmar la orden de entrega"""
        self._validate_stock_for_picking()
        return super().button_validate()