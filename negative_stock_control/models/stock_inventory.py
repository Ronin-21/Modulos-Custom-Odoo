from odoo import models
from odoo.exceptions import UserError


class StockQuant(models.Model):
    """Stock Quant - Validación de Ajustes de Inventario"""
    _inherit = 'stock.quant'

    def _validate_adjustment_stock(self):
        """Valida que los ajustes no dejen stock negativo"""
        productos_negativo = []

        for record in self:
            if record.product_id.type == 'service':
                continue

            # Si la cantidad disponible es negativa
            if record.quantity < 0:
                productos_negativo.append({
                    'nombre': record.product_id.name,
                    'cantidad': record.quantity,
                    'ubicacion': record.location_id.name
                })

        if productos_negativo:
            mensaje = "⚠️ AJUSTE DE INVENTARIO NO PERMITIDO\n\n"
            mensaje += "Los siguientes productos quedarían con stock negativo:\n\n"
            for prod in productos_negativo:
                mensaje += f"• {prod['nombre']}\n"
                mensaje += f"  Cantidad: {prod['cantidad']}\n"
                mensaje += f"  Ubicación: {prod['ubicacion']}\n\n"
            mensaje += "Por favor, corrija los valores antes de continuar."
            raise UserError(mensaje)

    def write(self, vals):
        """Valida ajustes al escribir en stock.quant"""
        result = super().write(vals)
        self._validate_adjustment_stock()
        return result