# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class SaleExchange(models.Model):
    _name = 'sale.exchange'
    _description = 'Cambio / Devolución de Pedido'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(string='Referencia', compute='_compute_name', store=True)
    order_id = fields.Many2one('sale.order', string='Pedido original', required=True, ondelete='restrict', index=True)
    session_id = fields.Many2one('sale.cashier.session', string='Sesión de caja', index=True)
    company_id = fields.Many2one('res.company', related='order_id.company_id', store=True)
    currency_id = fields.Many2one('res.currency', related='order_id.currency_id', store=True)
    partner_id = fields.Many2one('res.partner', related='order_id.partner_id', store=True)
    date = fields.Datetime(string='Fecha', default=fields.Datetime.now, readonly=True)
    user_id = fields.Many2one('res.users', string='Registrado por', default=lambda self: self.env.uid, readonly=True)
    reason = fields.Char(string='Motivo', required=True)

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Confirmado'),
        ('cancelled', 'Cancelado'),
    ], string='Estado', default='draft', required=True, tracking=True)

    return_line_ids = fields.One2many(
        'sale.exchange.return.line', 'exchange_id', string='Artículos que vuelven',
    )
    new_line_ids = fields.One2many(
        'sale.exchange.new.line', 'exchange_id', string='Artículos de reemplazo',
    )

    # Documentos generados
    credit_note_id = fields.Many2one('account.move', string='Nota de crédito', readonly=True, copy=False)
    new_invoice_id = fields.Many2one('account.move', string='Factura de reemplazo', readonly=True, copy=False)
    return_picking_id = fields.Many2one('stock.picking', string='Devolución de stock', readonly=True, copy=False)
    new_picking_id = fields.Many2one('stock.picking', string='Entrega de reemplazo', readonly=True, copy=False)

    # Diferencia monetaria
    amount_return = fields.Monetary(string='Total devuelto', compute='_compute_amounts', store=True, currency_field='currency_id')
    amount_new = fields.Monetary(string='Total nuevo', compute='_compute_amounts', store=True, currency_field='currency_id')
    amount_difference = fields.Monetary(string='Diferencia', compute='_compute_amounts', store=True, currency_field='currency_id',
        help='Positivo: el cliente debe pagar más. Negativo: se emite NC.')

    # Cobro pendiente de diferencia positiva
    supplement_invoice_id = fields.Many2one('account.move', string='Factura de diferencia', readonly=True, copy=False)
    supplement_paid = fields.Boolean(string='Diferencia cobrada', default=False, copy=False)

    @api.depends('order_id', 'date')
    def _compute_name(self):
        for rec in self:
            if rec.order_id:
                rec.name = _('Cambio %s') % rec.order_id.name
            else:
                rec.name = _('Cambio nuevo')

    @api.depends('return_line_ids.subtotal', 'new_line_ids.subtotal')
    def _compute_amounts(self):
        for rec in self:
            rec.amount_return = sum(rec.return_line_ids.mapped('subtotal'))
            rec.amount_new = sum(rec.new_line_ids.mapped('subtotal'))
            rec.amount_difference = rec.amount_new - rec.amount_return

    def action_view_credit_note(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.credit_note_id.id,
            'view_mode': 'form',
        }

    def action_view_new_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.new_invoice_id.id,
            'view_mode': 'form',
        }

    def action_view_return_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': self.return_picking_id.id,
            'view_mode': 'form',
        }

    def action_view_new_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': self.new_picking_id.id,
            'view_mode': 'form',
        }


class SaleExchangeReturnLine(models.Model):
    _name = 'sale.exchange.return.line'
    _description = 'Línea devuelta en Cambio'

    exchange_id = fields.Many2one('sale.exchange', required=True, ondelete='cascade')
    currency_id = fields.Many2one('res.currency', related='exchange_id.currency_id')
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unidad')
    quantity = fields.Float(string='Cantidad', default=1.0)
    price_unit = fields.Float(string='Precio unit.', digits='Product Price')
    tax_ids = fields.Many2many('account.tax', string='Impuestos')
    subtotal = fields.Monetary(string='Subtotal', compute='_compute_subtotal', store=True, currency_field='currency_id')
    account_id = fields.Many2one('account.account', string='Cuenta contable')

    @api.depends('quantity', 'price_unit', 'tax_ids')
    def _compute_subtotal(self):
        for line in self:
            taxes = line.tax_ids.compute_all(line.price_unit, quantity=line.quantity)
            line.subtotal = taxes['total_included']

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id
            self.tax_ids = self.product_id.taxes_id.filtered(
                lambda t: t.company_id == self.exchange_id.company_id
            )
            self.account_id = self.product_id.property_account_income_id or \
                self.product_id.categ_id.property_account_income_categ_id


class SaleExchangeNewLine(models.Model):
    _name = 'sale.exchange.new.line'
    _description = 'Línea nueva en Cambio'

    exchange_id = fields.Many2one('sale.exchange', required=True, ondelete='cascade')
    currency_id = fields.Many2one('res.currency', related='exchange_id.currency_id')
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unidad')
    quantity = fields.Float(string='Cantidad', default=1.0)
    price_unit = fields.Float(string='Precio unit.', digits='Product Price')
    tax_ids = fields.Many2many('account.tax', string='Impuestos')
    subtotal = fields.Monetary(string='Subtotal', compute='_compute_subtotal', store=True, currency_field='currency_id')
    account_id = fields.Many2one('account.account', string='Cuenta contable')

    @api.depends('quantity', 'price_unit', 'tax_ids')
    def _compute_subtotal(self):
        for line in self:
            taxes = line.tax_ids.compute_all(line.price_unit, quantity=line.quantity)
            line.subtotal = taxes['total_included']

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id
            self.tax_ids = self.product_id.taxes_id.filtered(
                lambda t: t.company_id == self.exchange_id.company_id
            )
            self.account_id = self.product_id.property_account_income_id or \
                self.product_id.categ_id.property_account_income_categ_id
