from odoo import models, fields


class PosPayment(models.Model):
    _inherit = "pos.payment"

    coupon_number = fields.Char(
        string="Número de Cupón",
        help="Número de cupón/comprobante de la transacción con tarjeta",
    )
    
    # ✅ NUEVO: Información detallada de la tarjeta y cuotas
    card_name = fields.Char(
        string="Tarjeta",
        help="Nombre de la tarjeta utilizada (Visa, Mastercard, Naranja, etc.)",
    )
    
    installments = fields.Integer(
        string="Cuotas",
        default=1,
        help="Número de cuotas del pago",
    )
    
    installment_percent = fields.Float(
        string="Recargo (%)",
        help="Porcentaje de recargo aplicado por las cuotas",
    )
    
    installment_plan_name = fields.Char(
        string="Plan",
        help="Nombre del plan de cuotas (ej: '3 Cuotas (15%)')",
    )

    def _export_for_ui(self, payment):
        result = super()._export_for_ui(payment)
        result.update({
            'coupon_number': payment.coupon_number or '',
            'card_name': payment.card_name or '',
            'installments': payment.installments or 1,
            'installment_percent': payment.installment_percent or 0.0,
            'installment_plan_name': payment.installment_plan_name or '',
        })
        return result