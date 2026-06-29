# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools


class CreditPartnerAnalysis(models.Model):
    _name = 'credit.partner.analysis'
    _description = 'Análisis de Crédito por Cliente'
    _auto = False
    _rec_name = 'partner_id'
    _order = 'amount_due desc'

    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', compute='_compute_currency_id')
    amount_due_accounting = fields.Monetary(
        string='Deuda contable',
        currency_field='currency_id',
        readonly=True,
    )
    amount_due_sale = fields.Monetary(
        string='Ventas sin facturar',
        currency_field='currency_id',
        readonly=True,
    )
    amount_due = fields.Monetary(
        string='Deuda total',
        currency_field='currency_id',
        readonly=True,
    )
    credit_warning = fields.Monetary(
        string='Límite advertencia',
        currency_field='currency_id',
        readonly=True,
    )
    credit_blocking = fields.Monetary(
        string='Límite bloqueo',
        currency_field='currency_id',
        readonly=True,
    )
    utilization_pct = fields.Float(
        string='Utilización %',
        digits=(6, 1),
        readonly=True,
    )
    credit_status = fields.Selection(
        [
            ('ok', 'OK'),
            ('over_warning', 'Cerca del límite'),
            ('over_limit', 'Sobre el límite'),
        ],
        string='Estado',
        readonly=True,
    )

    def action_open_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Facturas pendientes — %s' % self.partner_id.name,
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', 'child_of', self.partner_id.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'not in', ['paid', 'reversed']),
            ],
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_move_type': 'out_invoice',
            },
        }

    def get_formview_action(self, access_uid=None):
        self.ensure_one()
        return self.action_open_invoices()

    def action_open_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Órdenes sin facturar — %s' % self.partner_id.name,
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', 'child_of', self.partner_id.id),
                ('state', '=', 'sale'),
                ('invoice_status', '!=', 'invoiced'),
            ],
            'context': {
                'default_partner_id': self.partner_id.id,
            },
        }

    @api.depends('company_id')
    def _compute_currency_id(self):
        default_currency = self.env.company.currency_id
        for rec in self:
            rec.currency_id = rec.company_id.currency_id or default_currency

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW credit_partner_analysis AS (
                SELECT
                    rp.id                                                                          AS id,
                    rp.id                                                                          AS partner_id,
                    rp.company_id                                                                  AS company_id,
                    COALESCE(acct.receivable_balance, 0)                                          AS amount_due_accounting,
                    COALESCE(sale_agg.amount_due_sale, 0)                                         AS amount_due_sale,
                    COALESCE(acct.receivable_balance, 0) + COALESCE(sale_agg.amount_due_sale, 0)  AS amount_due,
                    COALESCE(rp.credit_warning, 0)                                                AS credit_warning,
                    COALESCE(rp.credit_blocking, 0)                                               AS credit_blocking,
                    CASE
                        WHEN COALESCE(rp.credit_blocking, 0) > 0 THEN
                            ROUND(
                                (
                                    (COALESCE(acct.receivable_balance, 0) + COALESCE(sale_agg.amount_due_sale, 0))
                                    / NULLIF(rp.credit_blocking, 0) * 100
                                )::numeric,
                                1
                            )
                        ELSE 0
                    END                                                                            AS utilization_pct,
                    CASE
                        WHEN COALESCE(rp.credit_blocking, 0) > 0
                             AND (COALESCE(acct.receivable_balance, 0) + COALESCE(sale_agg.amount_due_sale, 0))
                                 > rp.credit_blocking
                            THEN 'over_limit'
                        WHEN COALESCE(rp.credit_warning, 0) > 0
                             AND (COALESCE(acct.receivable_balance, 0) + COALESCE(sale_agg.amount_due_sale, 0))
                                 > rp.credit_warning
                            THEN 'over_warning'
                        ELSE 'ok'
                    END                                                                            AS credit_status
                FROM res_partner rp
                LEFT JOIN (
                    SELECT
                        aml.partner_id,
                        SUM(
                            CASE WHEN aa.account_type = 'asset_receivable'
                                 THEN aml.amount_residual
                                 ELSE 0
                            END
                        ) AS receivable_balance
                    FROM account_move_line aml
                    JOIN account_account aa ON aa.id = aml.account_id
                    WHERE aa.account_type IN ('asset_receivable', 'liability_payable')
                      AND aml.parent_state = 'posted'
                      AND aml.reconciled IS NOT TRUE
                    GROUP BY aml.partner_id
                ) acct ON acct.partner_id = rp.id
                LEFT JOIN (
                    SELECT partner_id, SUM(amount_total) AS amount_due_sale
                    FROM sale_order
                    WHERE state = 'sale'
                      AND invoice_status != 'invoiced'
                    GROUP BY partner_id
                ) sale_agg ON sale_agg.partner_id = rp.id
                WHERE rp.active = TRUE
                  AND rp.credit_check = TRUE
            )
        """)
