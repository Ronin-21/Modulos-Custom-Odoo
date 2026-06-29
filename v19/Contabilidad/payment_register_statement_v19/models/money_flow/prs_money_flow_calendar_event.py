# -*- coding: utf-8 -*-
from odoo import fields, models, tools, _


class PrsMoneyFlowCalendarEvent(models.Model):
    _name = 'prs.money.flow.calendar.event'
    _description = 'Calendario agrupado de Flujo de Dinero PRS'
    _auto = False
    _order = 'expected_date asc, journal_id, flow_group, id'

    name = fields.Char(string='Descripcion', readonly=True)
    expected_date = fields.Date(string='Fecha esperada', readonly=True)
    company_id = fields.Many2one('res.company', string='Empresa', readonly=True)
    journal_id = fields.Many2one('account.journal', string='Diario', readonly=True)
    flow_group = fields.Selection([('inbound', 'Ingresos'), ('outbound', 'Egresos')], string='Grupo', readonly=True)
    flow_type = fields.Selection(selection='_selection_flow_type', string='Tipo', readonly=True)
    source_tag = fields.Char(string='Agrupador', readonly=True)
    payment_method_label = fields.Char(string='Medio de pago', readonly=True)
    card_label = fields.Char(string='Tarjeta / Marca', readonly=True)
    plan_label = fields.Char(string='Plan', readonly=True)
    pos_config_label = fields.Char(string='Punto de venta', readonly=True)
    amount_gross = fields.Monetary(string='Bruto', currency_field='currency_id', readonly=True)
    amount_net = fields.Monetary(string='Neto', currency_field='currency_id', readonly=True)
    amount_signed = fields.Monetary(string='Importe con signo', currency_field='currency_id', readonly=True)
    flow_count = fields.Integer(string='Cantidad', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)

    def _selection_flow_type(self):
        return self.env['prs.money.flow']._fields['flow_type'].selection

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    x.id,
                    x.expected_date,
                    x.company_id,
                    x.journal_id,
                    x.flow_group,
                    x.flow_type,
                    x.source_tag,
                    x.payment_method_label,
                    x.card_label,
                    x.plan_label,
                    x.pos_config_label,
                    x.currency_id,
                    x.flow_count,
                    x.amount_gross,
                    x.amount_net,
                    x.amount_signed,
                    CONCAT(
                        CASE WHEN x.flow_group = 'outbound' THEN 'Egresos' ELSE 'Ingresos' END,
                        CASE WHEN x.journal_name <> '' THEN ' - ' || x.journal_name ELSE '' END,
                        CASE WHEN x.payment_method_label <> '' THEN ' - ' || x.payment_method_label ELSE '' END,
                        CASE WHEN x.card_label <> '' THEN ' - ' || x.card_label ELSE '' END,
                        CASE WHEN x.plan_label <> '' THEN ' - ' || x.plan_label ELSE '' END,
                        ' - ', x.flow_count::text, ' mov. - ', x.amount_signed::text
                    ) AS name
                FROM (
                    SELECT
                        MIN(f.id) AS id,
                        f.expected_date,
                        f.company_id,
                        f.journal_id,
                        f.flow_group,
                        f.flow_type,
                        COALESCE(f.source_tag, '') AS source_tag,
                        COALESCE(f.payment_method_label, '') AS payment_method_label,
                        COALESCE(f.card_label, '') AS card_label,
                        COALESCE(f.plan_label, '') AS plan_label,
                        COALESCE(f.pos_config_label, '') AS pos_config_label,
                        c.currency_id AS currency_id,
                        COALESCE(journal_name.name_text, '') AS journal_name,
                        COUNT(f.id)::integer AS flow_count,
                        SUM(f.amount_gross) AS amount_gross,
                        SUM(f.amount_net) AS amount_net,
                        SUM(f.amount_signed) AS amount_signed
                    FROM prs_money_flow f
                    JOIN res_company c ON c.id = f.company_id
                    LEFT JOIN account_journal j ON j.id = f.journal_id
                    LEFT JOIN LATERAL (
                        SELECT COALESCE(
                            to_jsonb(j.name)->>'es_AR',
                            to_jsonb(j.name)->>'es_ES',
                            to_jsonb(j.name)->>'en_US',
                            NULLIF(TRIM(BOTH '"' FROM to_jsonb(j.name)::text), 'null'),
                            ''
                        ) AS name_text
                    ) journal_name ON TRUE
                    WHERE f.state NOT IN ('cancelled', 'rejected')
                    GROUP BY
                        f.expected_date,
                        f.company_id,
                        f.journal_id,
                        f.flow_group,
                        f.flow_type,
                        COALESCE(f.source_tag, ''),
                        COALESCE(f.payment_method_label, ''),
                        COALESCE(f.card_label, ''),
                        COALESCE(f.plan_label, ''),
                        COALESCE(f.pos_config_label, ''),
                        c.currency_id,
                        COALESCE(journal_name.name_text, '')
                ) x
            )
        """ % self._table)

    def action_open_flow_details(self):
        self.ensure_one()
        domain = [
            ('expected_date', '=', self.expected_date),
            ('company_id', '=', self.company_id.id),
            ('journal_id', '=', self.journal_id.id),
            ('flow_group', '=', self.flow_group),
            ('flow_type', '=', self.flow_type),
            ('state', 'not in', ('cancelled', 'rejected')),
        ]
        for field_name, value in (
            ('source_tag', self.source_tag),
            ('payment_method_label', self.payment_method_label),
            ('card_label', self.card_label),
            ('plan_label', self.plan_label),
            ('pos_config_label', self.pos_config_label),
        ):
            if value:
                domain.append((field_name, '=', value))
            else:
                domain = ['|', (field_name, '=', False), (field_name, '=', '')] + domain
        return {
            'type': 'ir.actions.act_window',
            'name': _('Detalle de flujo'),
            'res_model': 'prs.money.flow',
            'view_mode': 'list,form,pivot,graph',
            'domain': domain,
            'target': 'current',
        }
