# -*- coding: utf-8 -*-
from odoo import models, fields, tools


class SofPaymentReport(models.Model):
    """Análisis de Cobros del flujo SOF (estilo POS).

    Tabla virtual (SQL view) sobre los pagos de caja: un registro por pago,
    clasificado por tipo de medio (efectivo/tarjeta/banco/cheque/cuenta corriente)
    a partir del plan de pago y del diario. Permite pivot/gráfico/lista por
    sesión, cajero, sucursal, vendedor y medio de pago.
    """
    _name = 'sof.payment.report'
    _description = 'Análisis de Cobros (SOF)'
    _auto = False
    _order = 'date desc'

    date = fields.Date(string='Fecha', readonly=True)
    amount = fields.Monetary(string='Importe', readonly=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)
    payment_count = fields.Integer(string='# Pagos', readonly=True)
    journal_id = fields.Many2one('account.journal', string='Diario / Medio', readonly=True)
    tender_type = fields.Selection([
        ('cash', 'Efectivo'),
        ('card', 'Tarjeta'),
        ('bank', 'Banco / Transferencia'),
        ('check', 'Cheque'),
        ('cc', 'Cuenta Corriente'),
        ('other', 'Otro'),
    ], string='Tipo de medio', readonly=True)
    direction = fields.Selection([
        ('inbound', 'Cobro'),
        ('outbound', 'Reintegro'),
    ], string='Movimiento', readonly=True)
    session_id = fields.Many2one('sale.cashier.session', string='Sesión', readonly=True)
    cashier_id = fields.Many2one('res.users', string='Cajero', readonly=True)
    user_id = fields.Many2one('res.users', string='Vendedor', readonly=True)
    order_id = fields.Many2one('sale.order', string='Pedido', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    financing_plan_id = fields.Many2one('sale.financing.plan', string='Plan de pago', readonly=True)
    company_id = fields.Many2one('res.company', string='Sucursal', readonly=True)
    card_name = fields.Char(string='Tarjeta / Red', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    p.id AS id,
                    p.date AS date,
                    CASE WHEN p.payment_type = 'outbound' THEN -p.amount ELSE p.amount END AS amount,
                    p.currency_id AS currency_id,
                    1 AS payment_count,
                    p.journal_id AS journal_id,
                    CASE
                        WHEN fp.is_check_payment THEN 'check'
                        WHEN fp.is_pay_later THEN 'cc'
                        WHEN (fp.card_name IS NOT NULL AND fp.card_name <> '') THEN 'card'
                        WHEN j.type = 'cash' THEN 'cash'
                        WHEN j.type = 'bank' THEN 'bank'
                        ELSE 'other'
                    END AS tender_type,
                    p.payment_type AS direction,
                    p.op_cashier_session_id AS session_id,
                    sess.cashier_id AS cashier_id,
                    so.user_id AS user_id,
                    p.op_sale_order_id AS order_id,
                    p.partner_id AS partner_id,
                    p.op_financing_plan_id AS financing_plan_id,
                    p.company_id AS company_id,
                    fp.card_name AS card_name
                FROM account_payment p
                JOIN account_journal j ON j.id = p.journal_id
                LEFT JOIN sale_financing_plan fp ON fp.id = p.op_financing_plan_id
                LEFT JOIN sale_order so ON so.id = p.op_sale_order_id
                LEFT JOIN sale_cashier_session sess ON sess.id = p.op_cashier_session_id
                WHERE p.op_cashier_session_id IS NOT NULL
                  AND p.state IN ('in_process', 'paid')
            )
        """ % self._table)
