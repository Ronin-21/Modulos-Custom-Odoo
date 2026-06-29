# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class SaleCashierCashMove(models.Model):
    _name = 'sale.cashier.cash.move'
    _description = 'Movimiento de Efectivo en Sesión de Caja'
    _order = 'date asc, id asc'
    _rec_name = 'reason'

    session_id = fields.Many2one(
        'sale.cashier.session', string='Sesión',
        required=True, ondelete='cascade', index=True,
    )
    move_type = fields.Selection(
        [('in', 'Ingreso'), ('out', 'Egreso')],
        string='Tipo', required=True,
    )
    amount = fields.Monetary(string='Monto', required=True, currency_field='currency_id')
    reason = fields.Char(string='Motivo', required=True)
    date = fields.Datetime(string='Fecha/Hora', default=fields.Datetime.now, readonly=True)
    user_id = fields.Many2one(
        'res.users', string='Usuario',
        default=lambda self: self.env.uid, readonly=True,
    )
    company_id = fields.Many2one(related='session_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(related='session_id.currency_id', store=True, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.user.has_group('sale_op_flow.group_sale_supervisor'):
            try:
                raw = self.env['ir.config_parameter'].sudo().get_param(
                    'sale_op_flow.allow_cashier_cash_moves', '0')
                allowed = str(raw).lower() in ('1', 'true', 't', 'yes', 'y', 'on', 'si', 'sí')
            except Exception:
                allowed = False
            if not allowed:
                raise UserError(_('No tenés permisos para registrar movimientos de efectivo.'))
        return super().create(vals_list)

    @api.constrains('amount')
    def _check_amount_positive(self):
        for move in self:
            if move.amount <= 0:
                raise ValidationError(_('El monto debe ser mayor a cero.'))
