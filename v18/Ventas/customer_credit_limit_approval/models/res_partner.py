# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Moneda de la compañía para usarla en los Monetary
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
        store=False,
    )

    credit_check = fields.Boolean(
        string='Crédito activo ?',
        help='Activa la validación de límite de crédito para este cliente.'
    )
    credit_warning = fields.Monetary(
        string='Monto de advertencia ?',
        currency_field='company_currency_id',
        help='Al superar este monto se puede advertir pero no necesariamente bloquear.'
    )
    credit_blocking = fields.Monetary(
        string='Monto de bloqueo ?',
        currency_field='company_currency_id',
        help='Al superar este monto la orden se bloqueará y deberá aprobarse.'
    )

    # ─────────────────────────────────────────────
    # DESGLOSE DE DEUDA
    # ─────────────────────────────────────────────
    amount_due_accounting = fields.Monetary(
        string='Deuda facturada (contable)',
        currency_field='company_currency_id',
        compute='_compute_credit_components',
        store=False,
        help='Sólo facturas/movimientos en cuentas a cobrar (debit - credit).'
    )
    amount_due_sale = fields.Monetary(
        string='Ventas confirmadas sin facturar',
        currency_field='company_currency_id',
        compute='_compute_credit_components',
        store=False,
        help='Órdenes de venta en estado Venta no totalmente facturadas.'
    )
    amount_due = fields.Monetary(
        string='Deuda Total ?',
        currency_field='company_currency_id',
        compute='_compute_credit_components',
        store=False,
        help='Suma de deuda contable + ventas sin facturar. El módulo POS suma además los tickets de Cuenta Corriente.'
    )

    @api.depends(
        'credit',
        'debit',
        'sale_order_ids.state',
        'sale_order_ids.invoice_status',
        'sale_order_ids.amount_total',
    )
    def _compute_credit_components(self):
        SaleOrder = self.env['sale.order']
        for partner in self:
            accounting = (partner.credit or 0.0) - (partner.debit or 0.0)

            sale_orders = SaleOrder.search([
                ('partner_id', '=', partner.id),
                ('state', '=', 'sale'),
                ('invoice_status', '!=', 'invoiced'),
            ])
            sale_amount = sum(sale_orders.mapped('amount_total'))

            partner.amount_due_accounting = accounting
            partner.amount_due_sale = sale_amount
            partner.amount_due = accounting + sale_amount

    def action_open_credit_statement(self):
        self.ensure_one()
        wizard = self.env['credit.statement.wizard'].create({'partner_id': self.id})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Estado de Cuenta',
            'res_model': 'credit.statement.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @api.constrains('credit_warning', 'credit_blocking')
    def _check_credit_amount(self):
        for partner in self:
            warning = partner.credit_warning or 0.0
            blocking = partner.credit_blocking or 0.0

            if warning < 0 or blocking < 0:
                raise ValidationError(
                    _('Los montos de advertencia y bloqueo no pueden ser negativos.')
                )

            if warning and blocking and warning > blocking:
                raise ValidationError(
                    _('El monto de advertencia (%s) no puede ser mayor que el monto de bloqueo (%s).')
                    % (warning, blocking)
                )


class ResCompany(models.Model):
    _inherit = 'res.company'

    accountant_email = fields.Char(string='Accountant email')
