# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SaleCommissionLine(models.Model):
    _name = 'sale.commission.line'
    _description = 'Línea de Comisión'
    _order = 'payment_date desc, id desc'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        readonly=True,
        default='Nueva comisión',
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='company_id.currency_id',
        store=True,
    )

    salesperson_id = fields.Many2one(
        'res.users',
        string='Vendedor',
        required=True,
        index=True,
        tracking=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        index=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de venta',
        ondelete='restrict',
        index=True,
    )
    move_id = fields.Many2one(
        'account.move',
        string='Factura',
        required=True,
        ondelete='restrict',
        index=True,
    )
    settlement_id = fields.Many2one(
        'sale.commission.settlement',
        string='Liquidación',
        ondelete='restrict',
        index=True,
        readonly=True,
    )

    invoice_date = fields.Date(
        string='Fecha de factura',
        related='move_id.invoice_date',
        store=True,
    )
    payment_date = fields.Date(
        string='Fecha de pago efectivo',
        required=True,
    )
    commission_base_amount = fields.Monetary(
        string='Base de comisión',
        currency_field='currency_id',
    )
    commission_percent = fields.Float(
        string='Porcentaje (%)',
        digits=(5, 2),
    )
    commission_amount = fields.Monetary(
        string='Importe de comisión',
        currency_field='currency_id',
    )
    paid_amount_considered = fields.Monetary(
        string='Importe cobrado considerado',
        currency_field='currency_id',
        help='Importe efectivo considerado para el cálculo en modo proporcional.',
    )

    state = fields.Selection([
        ('draft', 'Pendiente de pago'),
        ('earned', 'Ganada'),
        ('settled', 'Confirmada'),
        ('paid', 'Pagada'),
        ('adjusted', 'Ajustada'),
        ('cancelled', 'Cancelada'),
    ], string='Estado', default='draft', required=True,
        tracking=True, index=True)

    notes = fields.Text(string='Notas')

    # FIX: Se eliminó el SQL constraint UNIQUE(move_id, sale_order_id, active)
    # porque en PostgreSQL NULL != NULL, lo que permite duplicados cuando
    # sale_order_id es NULL. Se reemplaza por un @api.constrains en Python.

    @api.constrains('move_id', 'sale_order_id', 'active', 'state')
    def _check_unique_commission(self):
        """
        FIX: Validación de unicidad en Python en lugar de SQL constraint,
        para manejar correctamente el caso donde sale_order_id es NULL.
        Una factura solo puede tener una comisión activa no cancelada.
        """
        for rec in self:
            if not rec.active or rec.state == 'cancelled':
                continue
            domain = [
                ('move_id', '=', rec.move_id.id),
                ('active', '=', True),
                ('state', 'not in', ('cancelled',)),
                ('id', '!=', rec.id),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    f'Ya existe una comisión activa para la factura {rec.move_id.name}.'
                )

    @api.constrains('commission_percent')
    def _check_percent(self):
        for rec in self:
            if rec.commission_percent < 0 or rec.commission_percent > 100:
                raise ValidationError(
                    'El porcentaje de comisión debe estar entre 0 y 100.'
                )

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', 'Nueva comisión') == 'Nueva comisión':
                vals['name'] = seq.next_by_code('sale.commission.line') or 'COM-???'
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_cancelled(self):
        """
        FIX: Protege el borrado físico de comisiones en estados activos.
        Solo se permite eliminar comisiones canceladas.
        """
        protected = self.filtered(lambda r: r.state not in ('cancelled',))
        if protected:
            names = ', '.join(protected.mapped('name'))
            raise ValidationError(
                f'No se puede eliminar una comisión que no esté cancelada: {names}. '
                f'Primero cancelá la comisión y luego eliminala si es necesario.'
            )

    def action_cancel(self):
        for rec in self:
            if rec.state in ('paid',):
                raise ValidationError(
                    'No se puede cancelar una comisión ya pagada.'
                )
            rec.state = 'cancelled'

    def action_reset_to_earned(self):
        for rec in self:
            if rec.state == 'cancelled':
                rec.state = 'earned'

    @api.model
    def _get_commission_percent(self, salesperson, company=None):
        if salesperson.use_custom_commission and salesperson.commission_percent > 0:
            return salesperson.commission_percent
        config = self.env['sale.commission.config'].get_config(company)
        return config.default_commission_percent

    @api.model
    def _get_base_amount(self, move, config=None):
        if config is None:
            config = self.env['sale.commission.config'].get_config(move.company_id)
        if config.commission_base == 'amount_untaxed':
            return move.amount_untaxed
        return move.amount_total

    @api.model
    def _round_commission(self, amount, config=None, company=None):
        if config is None:
            config = self.env['sale.commission.config'].get_config(company)
        rounding = config.rounding
        if rounding == 'no':
            return amount
        if rounding == '1':
            return round(amount, 0)
        return round(amount, 2)
