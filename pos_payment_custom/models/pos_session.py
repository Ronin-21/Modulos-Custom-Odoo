# -*- coding: utf-8 -*-
from odoo import models


class PosSession(models.Model):
    _inherit = "pos.session"

    def _loader_params_pos_payment_method(self):
        res = super()._loader_params_pos_payment_method()
        search_params = res.get("search_params") or {}
        fields = search_params.get("fields") or []
        if not isinstance(fields, list):
            fields = list(fields)

        for fname in (
            "apply_adjustment",
            "adjustment_type",
            "adjustment_product_id",
            "cards_config",
        ):
            if fname not in fields:
                fields.append(fname)

        search_params["fields"] = fields
        res["search_params"] = search_params
        return res

    def _loader_params_pos_order(self):
        res = super()._loader_params_pos_order()
        search_params = res.get("search_params") or {}
        fields = search_params.get("fields") or []
        if not isinstance(fields, list):
            fields = list(fields)

        if "coupon_numbers" not in fields:
            fields.append("coupon_numbers")

        search_params["fields"] = fields
        res["search_params"] = search_params
        return res

    def _loader_params_pos_payment(self):
        """Cargar campos de tarjeta en los pagos"""
        res = super()._loader_params_pos_payment()
        search_params = res.get("search_params") or {}
        fields = search_params.get("fields") or []
        if not isinstance(fields, list):
            fields = list(fields)

        for fname in (
            "coupon_number",
            "card_name",
            "installments",
            "installment_percent",
            "installment_plan_name",
        ):
            if fname not in fields:
                fields.append(fname)

        search_params["fields"] = fields
        res["search_params"] = search_params
        return res

    def get_card_payment_totals(self):
        """Totales de pagos CON tarjeta por método + tarjeta + plan.
        
        SOLO retorna pagos CON tarjeta (para el desglose detallado).
        """
        self.ensure_one()
        self.env.cr.execute(
            """
            SELECT
                ppm.id AS payment_method_id,
                ppm.name AS payment_method_name,
                pp.card_name,
                pp.installment_plan_name,
                pp.installments,
                COALESCE(pp.installment_percent, 0) AS installment_percent,
                COUNT(pp.id) AS transaction_count,
                SUM(pp.amount) AS total_amount,
                STRING_AGG(DISTINCT pp.coupon_number, ', ' ORDER BY pp.coupon_number) AS coupons
            FROM pos_payment pp
            INNER JOIN pos_order po ON pp.pos_order_id = po.id
            INNER JOIN pos_payment_method ppm ON pp.payment_method_id = ppm.id
            WHERE po.session_id = %s
              AND po.state IN ('paid', 'done', 'invoiced')
              AND pp.card_name IS NOT NULL
              AND pp.card_name != ''
            GROUP BY
                ppm.id,
                ppm.name,
                pp.card_name,
                pp.installment_plan_name,
                pp.installments,
                pp.installment_percent
            ORDER BY
                ppm.name,
                pp.card_name,
                pp.installments
            """,
            (self.id,),
        )
        return self.env.cr.dictfetchall()

    def get_all_payment_totals(self):
        """Totales de TODOS los pagos (con y sin tarjeta).
        
        Agrupa por método de pago y muestra totales generales.
        """
        self.ensure_one()
        self.env.cr.execute(
            """
            SELECT
                ppm.id AS payment_method_id,
                ppm.name AS payment_method_name,
                COUNT(pp.id) AS transaction_count,
                SUM(pp.amount) AS total_amount,
                COUNT(CASE WHEN pp.card_name IS NOT NULL AND pp.card_name != '' THEN 1 END) AS has_card_details
            FROM pos_payment pp
            INNER JOIN pos_order po ON pp.pos_order_id = po.id
            INNER JOIN pos_payment_method ppm ON pp.payment_method_id = ppm.id
            WHERE po.session_id = %s
              AND po.state IN ('paid', 'done', 'invoiced')
            GROUP BY
                ppm.id,
                ppm.name
            ORDER BY
                ppm.name
            """,
            (self.id,),
        )
        return self.env.cr.dictfetchall()

    def get_non_card_payment_details(self):
        """✅ MEJORADO: Desglose de pagos SIN tarjeta AGRUPADOS.
        
        Agrupa por método de pago en lugar de por orden individual.
        Identifica si hay pagos mixtos en el grupo.
        """
        self.ensure_one()
        self.env.cr.execute(
            """
            SELECT
                ppm.id AS payment_method_id,
                ppm.name AS payment_method_name,
                COUNT(pp.id) AS transaction_count,
                SUM(pp.amount) AS total_amount,
                -- Contar cuántos son pagos mixtos vs directos
                COUNT(CASE 
                    WHEN (SELECT COUNT(DISTINCT pp2.payment_method_id) 
                        FROM pos_payment pp2 
                        WHERE pp2.pos_order_id = pp.pos_order_id) > 1 
                    THEN 1 
                END) AS mixed_count,
                -- Referencias de órdenes (para debugging si es necesario)
                STRING_AGG(DISTINCT po.pos_reference, ', ' ORDER BY po.pos_reference) AS order_references
            FROM pos_payment pp
            INNER JOIN pos_order po ON pp.pos_order_id = po.id
            INNER JOIN pos_payment_method ppm ON pp.payment_method_id = ppm.id
            WHERE po.session_id = %s
            AND po.state IN ('paid', 'done', 'invoiced')
            AND (pp.card_name IS NULL OR pp.card_name = '')
            GROUP BY
                ppm.id,
                ppm.name
            ORDER BY
                ppm.name
            """,
            (self.id,),
        )
        return self.env.cr.dictfetchall()