# -*- coding: utf-8 -*-
from odoo import models, fields, tools


class SofSaleReport(models.Model):
    """Análisis de Ventas del flujo SOF.

    Tabla virtual (SQL view) a nivel de línea de pedido, al estilo del reporte
    de Ventas nativo. Permite pivot/gráfico/lista por vendedor, sucursal,
    producto, categoría, cliente, plan de pago y estado operativo.
    """
    _name = 'sof.sale.report'
    _description = 'Análisis de Ventas (SOF)'
    _auto = False
    _order = 'date desc'

    date = fields.Date(string='Fecha', readonly=True)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    categ_id = fields.Many2one('product.category', string='Categoría', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    user_id = fields.Many2one('res.users', string='Vendedor', readonly=True)
    company_id = fields.Many2one('res.company', string='Sucursal', readonly=True)
    order_id = fields.Many2one('sale.order', string='Pedido', readonly=True)
    financing_plan_id = fields.Many2one('sale.financing.plan', string='Plan de pago', readonly=True)
    final_payment_journal_id = fields.Many2one('account.journal', string='Cobrado con', readonly=True)
    operational_state = fields.Selection([
        ('quotation', 'Presupuesto'),
        ('confirmed', 'Confirmado'),
        ('prepared', 'Preparado'),
        ('paid', 'Pagado'),
        ('in_delivery', 'En reparto'),
        ('dispatched', 'Despachado'),
    ], string='Estado operativo', readonly=True)
    product_uom_qty = fields.Float(string='Cantidad', readonly=True)
    price_subtotal = fields.Monetary(string='Importe (sin IVA)', readonly=True, currency_field='currency_id')
    price_total = fields.Monetary(string='Importe (con IVA)', readonly=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)
    nbr = fields.Integer(string='# Líneas', readonly=True)
    order_count = fields.Float(string='# Pedidos', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    l.id AS id,
                    so.date_order::date AS date,
                    l.product_id AS product_id,
                    pt.categ_id AS categ_id,
                    so.partner_id AS partner_id,
                    so.user_id AS user_id,
                    so.company_id AS company_id,
                    so.id AS order_id,
                    so.operational_state AS operational_state,
                    so.financing_plan_id AS financing_plan_id,
                    so.final_payment_journal_id AS final_payment_journal_id,
                    l.product_uom_qty AS product_uom_qty,
                    l.price_subtotal AS price_subtotal,
                    l.price_total AS price_total,
                    so.currency_id AS currency_id,
                    1 AS nbr,
                    (1.0 / NULLIF(count(*) OVER (PARTITION BY l.order_id), 0)) AS order_count
                FROM sale_order_line l
                JOIN sale_order so ON so.id = l.order_id
                JOIN product_product pp ON pp.id = l.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE so.is_sof_order = TRUE
                  AND so.operational_state <> 'cancelled'
                  AND l.display_type IS NULL
                  AND l.product_id IS NOT NULL
            )
        """ % self._table)
