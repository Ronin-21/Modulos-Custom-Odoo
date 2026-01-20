# -*- coding: utf-8 -*-
from odoo import models, fields, api


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

    # ✅ Resumen de cupones del pedido (para mostrar en ticket list + buscar)
    coupon_numbers = fields.Char(
        string="Nº Cupón",
        compute="_compute_coupon_numbers",
        store=True,
        index=True,
        help="Números de cupón detectados en los pagos del pedido (ej: 123-1234).",
    )

    @api.depends("payment_ids", "payment_ids.coupon_number")
    def _compute_coupon_numbers(self):
        """Concatenar todos los números de cupón de los pagos"""
        for order in self:
            numbers = []
            for payment in order.payment_ids:
                cn = (payment.coupon_number or "").strip()
                if cn and cn not in numbers:
                    numbers.append(cn)
            order.coupon_numbers = ", ".join(numbers) if numbers else ""

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

    def _payment_fields(self, order, ui_paymentline):
        """Guardar número de cupón y datos de la tarjeta en los pagos"""
        res = super()._payment_fields(order, ui_paymentline)
        res.update({
            "coupon_number": ui_paymentline.get("coupon_number", "") or "",
            # ✅ Guardar información de tarjeta y cuotas
            "card_name": ui_paymentline.get("card_name", "") or "",
            "installments": ui_paymentline.get("installments", 1) or 1,
            "installment_percent": ui_paymentline.get("installment_percent", 0.0) or 0.0,
            "installment_plan_name": ui_paymentline.get("installment_plan_name", "") or "",
        })
        return res
    
    def write(self, vals):
        """Forzar recálculo de cupones después de guardar pagos"""
        res = super().write(vals)
        # Si se modificaron los pagos, recalcular cupones
        if 'payment_ids' in vals:
            self._compute_coupon_numbers()
        return res
    
    def action_recalculate_coupons(self):
        """Acción para recalcular manualmente los cupones de órdenes existentes"""
        for order in self:
            order._compute_coupon_numbers()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Cupones Recalculados',
                'message': f'{len(self)} orden(es) actualizadas correctamente',
                'type': 'success',
                'sticky': False,
            }
        }