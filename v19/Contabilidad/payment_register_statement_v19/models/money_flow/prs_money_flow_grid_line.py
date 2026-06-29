# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class PrsMoneyFlowGridLine(models.Model):
    _name = 'prs.money.flow.grid.line'
    _description = 'Grilla Cash Flow PRS'
    _auto = False
    _order = 'flow_group, journal_id, source_tag, payment_method_label, card_label, plan_label, id'

    company_id = fields.Many2one('res.company', string='Empresa', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)
    journal_id = fields.Many2one('account.journal', string='Diario', readonly=True)
    flow_group = fields.Selection([('inbound', 'Ingresos'), ('outbound', 'Egresos')], string='Grupo', readonly=True)
    flow_type = fields.Selection(selection='_selection_flow_type', string='Tipo', readonly=True)
    source_tag = fields.Char(string='Agrupador', readonly=True)
    payment_method_label = fields.Char(string='Medio de pago', readonly=True)
    card_label = fields.Char(string='Tarjeta / Marca', readonly=True)
    plan_label = fields.Char(string='Plan', readonly=True)
    pos_config_label = fields.Char(string='Punto de venta', readonly=True)
    line_label = fields.Char(string='Descripcion de Dias', readonly=True)
    flow_count = fields.Integer(string='Cantidad', readonly=True)
    initial_balance = fields.Monetary(string='Saldo Inicial', currency_field='currency_id', readonly=True)
    day_00 = fields.Monetary(string='Dia 00', currency_field='currency_id', readonly=True)
    balance_00 = fields.Monetary(string='Saldo 00', currency_field='currency_id', readonly=True)
    day_01 = fields.Monetary(string='Dia 01', currency_field='currency_id', readonly=True)
    balance_01 = fields.Monetary(string='Saldo 01', currency_field='currency_id', readonly=True)
    day_02 = fields.Monetary(string='Dia 02', currency_field='currency_id', readonly=True)
    balance_02 = fields.Monetary(string='Saldo 02', currency_field='currency_id', readonly=True)
    day_03 = fields.Monetary(string='Dia 03', currency_field='currency_id', readonly=True)
    balance_03 = fields.Monetary(string='Saldo 03', currency_field='currency_id', readonly=True)
    day_04 = fields.Monetary(string='Dia 04', currency_field='currency_id', readonly=True)
    balance_04 = fields.Monetary(string='Saldo 04', currency_field='currency_id', readonly=True)
    day_05 = fields.Monetary(string='Dia 05', currency_field='currency_id', readonly=True)
    balance_05 = fields.Monetary(string='Saldo 05', currency_field='currency_id', readonly=True)
    day_06 = fields.Monetary(string='Dia 06', currency_field='currency_id', readonly=True)
    balance_06 = fields.Monetary(string='Saldo 06', currency_field='currency_id', readonly=True)
    day_07 = fields.Monetary(string='Dia 07', currency_field='currency_id', readonly=True)
    balance_07 = fields.Monetary(string='Saldo 07', currency_field='currency_id', readonly=True)
    day_08 = fields.Monetary(string='Dia 08', currency_field='currency_id', readonly=True)
    balance_08 = fields.Monetary(string='Saldo 08', currency_field='currency_id', readonly=True)
    day_09 = fields.Monetary(string='Dia 09', currency_field='currency_id', readonly=True)
    balance_09 = fields.Monetary(string='Saldo 09', currency_field='currency_id', readonly=True)
    day_10 = fields.Monetary(string='Dia 10', currency_field='currency_id', readonly=True)
    balance_10 = fields.Monetary(string='Saldo 10', currency_field='currency_id', readonly=True)
    day_11 = fields.Monetary(string='Dia 11', currency_field='currency_id', readonly=True)
    balance_11 = fields.Monetary(string='Saldo 11', currency_field='currency_id', readonly=True)
    day_12 = fields.Monetary(string='Dia 12', currency_field='currency_id', readonly=True)
    balance_12 = fields.Monetary(string='Saldo 12', currency_field='currency_id', readonly=True)
    day_13 = fields.Monetary(string='Dia 13', currency_field='currency_id', readonly=True)
    balance_13 = fields.Monetary(string='Saldo 13', currency_field='currency_id', readonly=True)
    day_14 = fields.Monetary(string='Dia 14', currency_field='currency_id', readonly=True)
    balance_14 = fields.Monetary(string='Saldo 14', currency_field='currency_id', readonly=True)

    def _selection_flow_type(self):
        return self.env['prs.money.flow']._fields['flow_type'].selection

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    ROW_NUMBER() OVER (ORDER BY x.flow_group, x.journal_id, x.source_tag, x.payment_method_label, x.card_label, x.plan_label) AS id,
                    x.company_id,
                    x.currency_id,
                    x.journal_id,
                    x.flow_group,
                    x.flow_type,
                    x.source_tag,
                    x.payment_method_label,
                    x.card_label,
                    x.plan_label,
                    x.pos_config_label,
                    CONCAT(
                        CASE WHEN x.flow_group = 'outbound' THEN 'Egresos' ELSE 'Ingresos' END,
                        ' / ', COALESCE(NULLIF(x.source_tag, ''), NULLIF(x.payment_method_label, ''), 'Sin agrupador'),
                        CASE WHEN x.card_label <> '' THEN ' / ' || x.card_label ELSE '' END,
                        CASE WHEN x.plan_label <> '' THEN ' / ' || x.plan_label ELSE '' END
                    ) AS line_label,
                    x.flow_count,
                    x.initial_balance,
                    x.day_00,
                    x.day_01,
                    x.day_02,
                    x.day_03,
                    x.day_04,
                    x.day_05,
                    x.day_06,
                    x.day_07,
                    x.day_08,
                    x.day_09,
                    x.day_10,
                    x.day_11,
                    x.day_12,
                    x.day_13,
                    x.day_14,
                    (x.initial_balance + x.day_00) AS balance_00,
                    (x.initial_balance + x.day_00 + x.day_01) AS balance_01,
                    (x.initial_balance + x.day_00 + x.day_01 + x.day_02) AS balance_02,
                    (x.initial_balance + x.day_00 + x.day_01 + x.day_02 + x.day_03) AS balance_03,
                    (x.initial_balance + x.day_00 + x.day_01 + x.day_02 + x.day_03 + x.day_04) AS balance_04,
                    (x.initial_balance + x.day_00 + x.day_01 + x.day_02 + x.day_03 + x.day_04 + x.day_05) AS balance_05,
                    (x.initial_balance + x.day_00 + x.day_01 + x.day_02 + x.day_03 + x.day_04 + x.day_05 + x.day_06) AS balance_06,
                    (x.initial_balance + x.day_00 + x.day_01 + x.day_02 + x.day_03 + x.day_04 + x.day_05 + x.day_06 + x.day_07) AS balance_07,
                    (x.initial_balance + x.day_00 + x.day_01 + x.day_02 + x.day_03 + x.day_04 + x.day_05 + x.day_06 + x.day_07 + x.day_08) AS balance_08,
                    (x.initial_balance + x.day_00 + x.day_01 + x.day_02 + x.day_03 + x.day_04 + x.day_05 + x.day_06 + x.day_07 + x.day_08 + x.day_09) AS balance_09,
                    (x.initial_balance + x.day_00 + x.day_01 + x.day_02 + x.day_03 + x.day_04 + x.day_05 + x.day_06 + x.day_07 + x.day_08 + x.day_09 + x.day_10) AS balance_10,
                    (x.initial_balance + x.day_00 + x.day_01 + x.day_02 + x.day_03 + x.day_04 + x.day_05 + x.day_06 + x.day_07 + x.day_08 + x.day_09 + x.day_10 + x.day_11) AS balance_11,
                    (x.initial_balance + x.day_00 + x.day_01 + x.day_02 + x.day_03 + x.day_04 + x.day_05 + x.day_06 + x.day_07 + x.day_08 + x.day_09 + x.day_10 + x.day_11 + x.day_12) AS balance_12,
                    (x.initial_balance + x.day_00 + x.day_01 + x.day_02 + x.day_03 + x.day_04 + x.day_05 + x.day_06 + x.day_07 + x.day_08 + x.day_09 + x.day_10 + x.day_11 + x.day_12 + x.day_13) AS balance_13,
                    (x.initial_balance + x.day_00 + x.day_01 + x.day_02 + x.day_03 + x.day_04 + x.day_05 + x.day_06 + x.day_07 + x.day_08 + x.day_09 + x.day_10 + x.day_11 + x.day_12 + x.day_13 + x.day_14) AS balance_14
                FROM (
                    SELECT
                        f.company_id,
                        c.currency_id,
                        f.journal_id,
                        f.flow_group,
                        f.flow_type,
                        COALESCE(f.source_tag, '') AS source_tag,
                        COALESCE(f.payment_method_label, '') AS payment_method_label,
                        COALESCE(f.card_label, '') AS card_label,
                        COALESCE(f.plan_label, '') AS plan_label,
                        COALESCE(f.pos_config_label, '') AS pos_config_label,
                        COUNT(f.id)::integer AS flow_count,
                        SUM(CASE WHEN f.expected_date < CURRENT_DATE THEN f.amount_signed ELSE 0 END) AS initial_balance,
                        SUM(CASE WHEN f.expected_date = CURRENT_DATE + 0 THEN f.amount_signed ELSE 0 END) AS day_00,
                        SUM(CASE WHEN f.expected_date = CURRENT_DATE + 1 THEN f.amount_signed ELSE 0 END) AS day_01,
                        SUM(CASE WHEN f.expected_date = CURRENT_DATE + 2 THEN f.amount_signed ELSE 0 END) AS day_02,
                        SUM(CASE WHEN f.expected_date = CURRENT_DATE + 3 THEN f.amount_signed ELSE 0 END) AS day_03,
                        SUM(CASE WHEN f.expected_date = CURRENT_DATE + 4 THEN f.amount_signed ELSE 0 END) AS day_04,
                        SUM(CASE WHEN f.expected_date = CURRENT_DATE + 5 THEN f.amount_signed ELSE 0 END) AS day_05,
                        SUM(CASE WHEN f.expected_date = CURRENT_DATE + 6 THEN f.amount_signed ELSE 0 END) AS day_06,
                        SUM(CASE WHEN f.expected_date = CURRENT_DATE + 7 THEN f.amount_signed ELSE 0 END) AS day_07,
                        SUM(CASE WHEN f.expected_date = CURRENT_DATE + 8 THEN f.amount_signed ELSE 0 END) AS day_08,
                        SUM(CASE WHEN f.expected_date = CURRENT_DATE + 9 THEN f.amount_signed ELSE 0 END) AS day_09,
                        SUM(CASE WHEN f.expected_date = CURRENT_DATE + 10 THEN f.amount_signed ELSE 0 END) AS day_10,
                        SUM(CASE WHEN f.expected_date = CURRENT_DATE + 11 THEN f.amount_signed ELSE 0 END) AS day_11,
                        SUM(CASE WHEN f.expected_date = CURRENT_DATE + 12 THEN f.amount_signed ELSE 0 END) AS day_12,
                        SUM(CASE WHEN f.expected_date = CURRENT_DATE + 13 THEN f.amount_signed ELSE 0 END) AS day_13,
                        SUM(CASE WHEN f.expected_date = CURRENT_DATE + 14 THEN f.amount_signed ELSE 0 END) AS day_14
                    FROM prs_money_flow f
                    JOIN res_company c ON c.id = f.company_id
                    WHERE f.state NOT IN ('cancelled', 'rejected')
                    GROUP BY
                        f.company_id,
                        c.currency_id,
                        f.journal_id,
                        f.flow_group,
                        f.flow_type,
                        COALESCE(f.source_tag, ''),
                        COALESCE(f.payment_method_label, ''),
                        COALESCE(f.card_label, ''),
                        COALESCE(f.plan_label, ''),
                        COALESCE(f.pos_config_label, '')
                ) x
            )
        """ % self._table)
