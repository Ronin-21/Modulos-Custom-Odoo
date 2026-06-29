# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ReportPosOrder(models.Model):
    _inherit = "report.pos.order"

    # ✅ Campos relacionados con tarjetas y cupones
    card_name = fields.Char(
        string="Tarjeta",
        readonly=True,
        help="Nombre de la tarjeta utilizada en el pago",
    )
    
    installment_plan_name = fields.Char(
        string="Plan de Cuotas",
        readonly=True,
        help="Nombre del plan (ej: 3 Cuotas (15%))",
    )
    
    installments = fields.Integer(
        string="Nº de Cuotas",
        readonly=True,
        help="Número de cuotas del pago",
    )
    
    coupon_numbers = fields.Char(
        string="Nº Cupón",
        readonly=True,
        help="Números de cupón del pedido",
    )
    
    has_coupon = fields.Boolean(
        string="Con Cupón",
        readonly=True,
        help="Indica si el pedido tiene número de cupón",
    )

    def _select(self):
        """Extender el SELECT del reporte"""
        select_str = super()._select()
        select_str += """,
            (SELECT STRING_AGG(DISTINCT pp.card_name, ', ')
             FROM pos_payment pp
             WHERE pp.pos_order_id = s.id 
             AND pp.card_name IS NOT NULL 
             AND pp.card_name != ''
            ) as card_name,
            (SELECT STRING_AGG(DISTINCT pp.installment_plan_name, ', ')
             FROM pos_payment pp
             WHERE pp.pos_order_id = s.id 
             AND pp.installment_plan_name IS NOT NULL 
             AND pp.installment_plan_name != ''
            ) as installment_plan_name,
            (SELECT MAX(pp.installments)
             FROM pos_payment pp
             WHERE pp.pos_order_id = s.id
            ) as installments,
            s.coupon_numbers as coupon_numbers,
            CASE 
                WHEN s.coupon_numbers IS NOT NULL AND s.coupon_numbers != '' 
                THEN TRUE 
                ELSE FALSE 
            END as has_coupon
        """
        return select_str

    def _group_by(self):
        """Extender el GROUP BY"""
        group_by_str = super()._group_by()
        group_by_str += """,
            s.coupon_numbers
        """
        return group_by_str