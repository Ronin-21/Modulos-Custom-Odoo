# -*- coding: utf-8 -*-
from odoo import models, fields


class _BoardStageMixin(models.AbstractModel):
    _name = 'sale.op.board.stage.mixin'
    _description = 'Mixin base para etapas de tablero operativo'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(default=0)
    count_orders = fields.Integer(string='Pedidos', compute='_compute_count_orders')

    def _get_domain(self):
        raise NotImplementedError

    def _compute_count_orders(self):
        for stage in self:
            stage.count_orders = self.env['sale.order'].search_count(stage._get_domain())

    def action_open_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': self._get_domain(),
            'context': {'create': False},
        }


class SaleDispatchStage(models.Model):
    _name = 'sale.dispatch.stage'
    _description = 'Etapa del Tablero de Despacho'
    _inherit = 'sale.op.board.stage.mixin'

    code = fields.Selection([
        ('confirmed', 'Confirmado'),
        ('prepared', 'Preparado'),
        ('paid', 'Pagado'),
        ('dispatched', 'Despachado'),
    ], string='Estado operativo', required=True)

    def _get_domain(self):
        self.ensure_one()
        today_str = fields.Date.today().strftime('%Y-%m-%d 00:00:00')
        domain = [('is_sof_order', '=', True), ('operational_state', '=', self.code)]
        if self.code == 'dispatched':
            domain.append(('dispatched_date', '>=', today_str))
        return domain


class SaleCashierBoardStage(models.Model):
    _name = 'sale.cashier.stage'
    _description = 'Etapa del Tablero de Caja'
    _inherit = 'sale.op.board.stage.mixin'

    code = fields.Selection([
        ('pending', 'Pendientes de Cobro'),
        ('collected_today', 'Cobrados Hoy'),
    ], string='Etapa', required=True)

    def _get_domain(self):
        self.ensure_one()
        today_str = fields.Date.today().strftime('%Y-%m-%d 00:00:00')
        if self.code == 'pending':
            return [('is_sof_order', '=', True), ('operational_state', 'in', ['confirmed', 'prepared']), ('cashier_session_id.state', '=', 'open')]
        if self.code == 'collected_today':
            return [
                ('is_sof_order', '=', True),
                ('operational_state', 'in', ['paid', 'dispatched']),
                ('collected_date', '>=', today_str),
            ]
        return []


class SaleVendorBoardStage(models.Model):
    _name = 'sale.vendor.stage'
    _description = 'Etapa del Tablero de Ventas'
    _inherit = 'sale.op.board.stage.mixin'

    code = fields.Selection([
        ('quotation', 'Cotizaciones'),
        ('active', 'Pedidos Activos'),
        ('ready', 'Por Entregar'),
        ('dispatched_today', 'Despachados Hoy'),
    ], string='Etapa', required=True)

    def _get_domain(self):
        self.ensure_one()
        today_str = fields.Date.today().strftime('%Y-%m-%d 00:00:00')
        if self.code == 'quotation':
            return [('is_sof_order', '=', True), ('operational_state', '=', 'quotation')]
        if self.code == 'active':
            return [('is_sof_order', '=', True), ('operational_state', 'in', ['confirmed', 'prepared'])]
        if self.code == 'ready':
            return [('is_sof_order', '=', True), ('operational_state', '=', 'paid')]
        if self.code == 'dispatched_today':
            return [
                ('is_sof_order', '=', True),
                ('operational_state', '=', 'dispatched'),
                ('dispatched_date', '>=', today_str),
            ]
        return []
