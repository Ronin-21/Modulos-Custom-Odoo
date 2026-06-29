from odoo import models
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    """MRP Production - Validación de Stock de Insumos"""
    _inherit = 'mrp.production'

    def _validate_stock_for_production(self):
        """Valida stock disponible para insumos en órdenes de fabricación"""
        insumos_sin_stock = []

        for line in self.move_raw_ids:
            if line.product_id.type == 'service':
                continue

            stock_disponible = line.product_id.qty_available
            cantidad_solicitada = line.product_uom_qty
            
            if stock_disponible < cantidad_solicitada:
                stock_pronosticado = line.product_id.virtual_available - line.product_id.qty_available
                insumos_sin_stock.append({
                    'nombre': line.product_id.name,
                    'stock': stock_disponible,
                    'pronosticado': max(0, stock_pronosticado),
                    'solicitado': cantidad_solicitada
                })

        if insumos_sin_stock:
            mensaje = "⚠️ STOCK INSUFICIENTE DE INSUMOS\n\n"
            mensaje += "Los siguientes insumos no tienen stock disponible para la fabricación:\n\n"
            for insumo in insumos_sin_stock:
                mensaje += f"• {insumo['nombre']}\n"
                mensaje += f"  Stock disponible: {insumo['stock']}"
                if insumo['pronosticado'] > 0:
                    mensaje += f" | Pronosticado: {insumo['pronosticado']}"
                mensaje += f" | Cantidad requerida: {insumo['solicitado']}\n\n"
            mensaje += "Por favor, verifique el inventario de insumos antes de continuar."
            raise UserError(mensaje)

    def action_confirm(self):
        """Valida stock de insumos antes de confirmar la orden de fabricación"""
        self._validate_stock_for_production()
        return super().action_confirm()