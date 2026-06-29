# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    commission_state = fields.Selection([
        ('not_commissionable', 'No comisionable'),
        ('pending_invoice', 'Pendiente de facturar'),
        ('pending_payment', 'Pendiente de pago'),
        ('earned', 'Comisión ganada'),
        ('settled', 'Liquidada'),
        ('paid', 'Comisión pagada'),
        ('partial', 'Parcialmente liquidada'),
    ], string='Estado comisión',
        compute='_compute_commission_state',
        store=True)

    commission_count = fields.Integer(
        string='Comisiones',
        compute='_compute_commission_count',
    )
    commission_amount_total = fields.Monetary(
        string='Total comisionado',
        compute='_compute_commission_count',
        currency_field='currency_id',
    )

    @api.depends('invoice_ids.commission_line_ids.state')
    def _compute_commission_state(self):
        for order in self:
            lines = order.invoice_ids.commission_line_ids.filtered(
                lambda l: l.active and l.state != 'cancelled')
            if not lines:
                if order.invoice_ids:
                    # Hay facturas pero sin comisión todavía (ej: módulo recién instalado)
                    order.commission_state = 'pending_payment'
                else:
                    order.commission_state = 'pending_invoice'
                continue

            states = set(lines.mapped('state'))

            if states <= {'paid'}:
                order.commission_state = 'paid'
            elif states <= {'settled', 'paid'}:
                order.commission_state = 'settled'
            elif 'settled' in states or 'paid' in states:
                order.commission_state = 'partial'
            elif 'earned' in states:
                order.commission_state = 'earned'
            elif states <= {'draft'}:
                # Todas las comisiones están en draft: facturada pero sin cobrar
                order.commission_state = 'pending_payment'
            else:
                order.commission_state = 'not_commissionable'

    def _compute_commission_count(self):
        for order in self:
            lines = order.invoice_ids.commission_line_ids.filtered(
                lambda l: l.active)
            order.commission_count = len(lines)
            order.commission_amount_total = sum(
                lines.mapped('commission_amount'))

    def action_view_commissions(self):
        self.ensure_one()
        move_ids = self.invoice_ids.ids
        return {
            'type': 'ir.actions.act_window',
            'name': 'Comisiones',
            'res_model': 'sale.commission.line',
            'view_mode': 'list,form',
            'domain': [('move_id', 'in', move_ids)],
        }
