from odoo import models
from odoo.exceptions import UserError


class StockTransfer(models.Model):
    """Stock Transfer - Validación de Stock para Traslados Internos"""
    _inherit = 'stock.picking'

    def _validate_stock_for_transfer(self):
        """Valida stock disponible en depósito origen para traslados internos"""
        if self.picking_type_id.code != 'internal':
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
            mensaje = "⚠️ STOCK INSUFICIENTE PARA TRASLADO\n\n"
            mensaje += "Los siguientes productos no tienen stock disponible en el depósito de origen:\n\n"
            for prod in productos_sin_stock:
                mensaje += f"• {prod['nombre']}\n"
                mensaje += f"  Stock disponible: {prod['stock']}"
                if prod['pronosticado'] > 0:
                    mensaje += f" | Pronosticado: {prod['pronosticado']}"
                mensaje += f" | Cantidad a trasladar: {prod['solicitado']}\n\n"
            mensaje += "Por favor, verifique el inventario antes de continuar."
            raise UserError(mensaje)

    def button_validate(self):
        """Valida stock antes de confirmar el traslado interno"""
        self._validate_stock_for_transfer()
        return super().button_validate()