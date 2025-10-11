from odoo import models, fields, api
from odoo.exceptions import ValidationError

class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    apply_adjustment = fields.Boolean(
        string="Aplicar descuento/recargo",
        help="Permite aplicar un descuento o recargo para el método de pago."
    )
    adjustment_type = fields.Selection(
        [
            ('discount', 'Descuento'),
            ('surcharge', 'Recargo')
        ],
        string="Tipo de ajuste",
        default='discount'
    )
    adjustment_value = fields.Float(
        string="Valor de ajuste (%)",
        help="Porcentaje de descuento o recargo aplicado sobre el total.",
        default=0.0
    )

    @api.constrains('adjustment_value')
    def _check_adjustment_values(self):
        for record in self:
            if record.adjustment_value < 0:
                raise ValidationError("El valor del ajuste no puede ser negativo.")
            if record.adjustment_value > 100:
                raise ValidationError("El valor del ajuste no puede ser mayor a 100%.")

    def calculate_adjustment(self, amount):
        """
        Calcula el descuento o recargo a aplicar
        
        Args:
            amount (float): Monto sobre el cual calcular el ajuste
            
        Returns:
            dict: {
                'adjustment_amount': float,
                'final_amount': float,
                'adjustment_type': str,
                'adjustment_percent': float
            }
        """
        self.ensure_one()
        
        result = {
            'adjustment_amount': 0.0,
            'final_amount': amount,
            'adjustment_type': self.adjustment_type,
            'adjustment_percent': 0.0
        }
        
        # No aplicar si está desactivado
        if not self.apply_adjustment or self.adjustment_value == 0.0:
            return result
        
        # Calcular el ajuste
        adjustment_amount = amount * (self.adjustment_value / 100)
        
        result['adjustment_percent'] = self.adjustment_value
        result['adjustment_amount'] = adjustment_amount
        
        if self.adjustment_type == 'discount':
            result['final_amount'] = amount - adjustment_amount
        else:  # surcharge
            result['final_amount'] = amount + adjustment_amount
        
        return result

    def apply_adjustment_to_order(self, order, amount):
        """
        Aplica el ajuste a una orden del POS
        Útil cuando necesites integrar directamente con órdenes
        """
        self.ensure_one()
        adjustment_info = self.calculate_adjustment(amount)
        return adjustment_info