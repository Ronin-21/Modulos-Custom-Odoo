# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class SaleCommissionSettlement(models.Model):
    _name = 'sale.commission.settlement'
    _description = 'Liquidación de Comisiones'
    _order = 'settlement_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        readonly=True,
        default='Nueva liquidación',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        store=True,
    )
    salesperson_id = fields.Many2one(
        'res.users',
        string='Vendedor',
        required=True,
        tracking=True,
    )
    date_from = fields.Date(string='Desde', required=True)
    date_to = fields.Date(string='Hasta', required=True)
    settlement_date = fields.Date(
        string='Fecha de liquidación',
        default=fields.Date.today,
    )

    line_ids = fields.One2many(
        'sale.commission.line',
        'settlement_id',
        string='Líneas de comisión',
    )
    total_base_amount = fields.Monetary(
        string='Total base',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    total_commission_amount = fields.Monetary(
        string='Total comisiones',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    line_count = fields.Integer(
        string='Nº de comisiones',
        compute='_compute_totals',
        store=True,
    )

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('confirmed', 'Confirmada'),
        ('paid', 'Pagada'),
        ('cancelled', 'Cancelada'),
    ], string='Estado', default='draft', tracking=True)

    notes = fields.Text(string='Notas')

    expense_account_id = fields.Many2one(
        'account.account',
        string='Cuenta gasto comisión',
    )
    payment_journal_id = fields.Many2one(
        'account.journal',
        string='Diario de pago',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        help='Diario desde el cual saldrá el dinero para pagar la comisión.',
    )
    payment_date = fields.Date(
        string='Fecha de pago',
    )
    payment_move_id = fields.Many2one(
        'account.move',
        string='Asiento de pago',
        readonly=True,
        copy=False,
    )
    payment_move_state = fields.Selection(
        related='payment_move_id.state',
        string='Estado pago',
        readonly=True,
    )
    start_date_applied = fields.Date(
        string='Fecha inicio aplicada',
        readonly=True,
        copy=False,
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from > rec.date_to:
                raise ValidationError(
                    'La fecha de inicio debe ser anterior a la fecha de fin.'
                )

    @api.depends('line_ids.commission_amount', 'line_ids.commission_base_amount', 'line_ids.state')
    def _compute_totals(self):
        for rec in self:
            lines = rec.line_ids.filtered(lambda l: l.state not in ('cancelled',))
            rec.total_base_amount = sum(lines.mapped('commission_base_amount'))
            rec.total_commission_amount = sum(lines.mapped('commission_amount'))
            rec.line_count = len(lines)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        company = self.env.company
        config = self.env['sale.commission.config'].get_config(company)
        if 'company_id' in fields_list and not vals.get('company_id'):
            vals['company_id'] = company.id
        if 'expense_account_id' in fields_list and not vals.get('expense_account_id') and config.expense_account_id:
            vals['expense_account_id'] = config.expense_account_id.id
        if 'payment_journal_id' in fields_list and not vals.get('payment_journal_id') and config.payment_journal_id:
            vals['payment_journal_id'] = config.payment_journal_id.id
        if 'start_date_applied' in fields_list and not vals.get('start_date_applied'):
            vals['start_date_applied'] = config.commission_start_date
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env['ir.sequence']
        for vals in vals_list:
            company_id = vals.get('company_id') or self.env.company.id
            config = self.env['sale.commission.config'].get_config(
                self.env['res.company'].browse(company_id)
            )
            if vals.get('name', 'Nueva liquidación') == 'Nueva liquidación':
                vals['name'] = seq.next_by_code('sale.commission.settlement') or 'LIQ-???'
            vals.setdefault('expense_account_id', config.expense_account_id.id if config.expense_account_id else False)
            vals.setdefault('payment_journal_id', config.payment_journal_id.id if config.payment_journal_id else False)
            vals.setdefault('start_date_applied', config.commission_start_date)
        return super().create(vals_list)

    def _prepare_payment_move_vals(self):
        self.ensure_one()
        amount = self.total_commission_amount
        pay_date = self.payment_date or self.settlement_date or fields.Date.today()
        journal_account = self.payment_journal_id.default_account_id
        if not journal_account:
            raise UserError(
                'El diario seleccionado no tiene cuenta contable por defecto.'
            )
        return {
            'move_type': 'entry',
            'date': pay_date,
            'ref': f'Pago comisiones {self.name} - {self.salesperson_id.name}',
            'company_id': self.company_id.id,
            'line_ids': [
                (0, 0, {
                    'name': f'Pago comisión {self.name}',
                    'account_id': self.expense_account_id.id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': f'Pago comisión {self.name}',
                    'account_id': journal_account.id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ],
        }

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError('Solo se pueden confirmar liquidaciones en borrador.')
            if not rec.line_ids:
                raise UserError('No hay comisiones en esta liquidación.')
            if rec.total_commission_amount <= 0:
                raise UserError('El total de comisiones debe ser mayor a cero.')

            rec.line_ids.filtered(lambda l: l.state == 'earned').write({'state': 'settled'})
            rec.state = 'confirmed'

    def action_register_payment(self):
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError('Solo se pueden pagar liquidaciones confirmadas.')
            if rec.payment_move_id:
                raise UserError('La liquidación ya tiene un asiento de pago.')
            if not rec.payment_journal_id:
                raise UserError('Debe seleccionar un diario de pago.')
            if not rec.expense_account_id:
                raise UserError('Debe definir la cuenta gasto comisión.')
            if rec.total_commission_amount <= 0:
                raise UserError('El total de comisiones debe ser mayor a cero.')

            move = self.env['account.move'].create(rec._prepare_payment_move_vals())
            move.action_post()

            rec.payment_move_id = move.id
            rec.payment_date = rec.payment_date or rec.settlement_date or fields.Date.today()
            rec.line_ids.filtered(lambda l: l.state == 'settled').write({'state': 'paid'})
            rec.state = 'paid'

    def action_cancel(self):
        for rec in self:
            if rec.state == 'paid':
                raise UserError(
                    'No se puede cancelar una liquidación ya pagada. Revertí primero el pago.'
                )
            rec.line_ids.write({'state': 'earned', 'settlement_id': False})
            rec.state = 'cancelled'

    def action_reverse_payment(self):
        for rec in self:
            if rec.state != 'paid':
                raise UserError('Solo se puede revertir el pago en liquidaciones pagadas.')
            if not rec.payment_move_id:
                raise UserError('La liquidación no tiene asiento de pago.')

            reverse_vals = {
                'date': fields.Date.today(),
                'ref': f'Reversa pago {rec.name}',
            }
            reversed_move = rec.payment_move_id._reverse_moves([reverse_vals], cancel=False)
            reversed_move.action_post()

            rec.line_ids.filtered(lambda l: l.state == 'paid').write({'state': 'settled'})
            rec.state = 'confirmed'
            rec.payment_move_id = False
            rec.payment_date = False

    def action_load_commissions(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(
                'Solo se pueden cargar comisiones en liquidaciones borrador.'
            )

        config = self.env['sale.commission.config'].get_config(self.company_id)
        start_date = config.commission_start_date

        domain = [
            ('salesperson_id', '=', self.salesperson_id.id),
            ('state', '=', 'earned'),
            ('settlement_id', '=', False),
            ('payment_date', '>=', self.date_from),
            ('payment_date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ]
        if start_date:
            domain.append(('payment_date', '>=', start_date))

        commissions = self.env['sale.commission.line'].search(domain)
        if not commissions:
            raise UserError(
                'No se encontraron comisiones ganadas para los criterios seleccionados.'
            )
        commissions.write({'settlement_id': self.id})
        return True

    def action_print_settlement(self):
        self.ensure_one()
        return self.env.ref(
            'sale_commission_custom.action_report_commission_settlement'
        ).report_action(self)

    def action_view_payment_move(self):
        self.ensure_one()
        if not self.payment_move_id:
            raise UserError('No hay asiento de pago generado.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asiento de pago',
            'res_model': 'account.move',
            'res_id': self.payment_move_id.id,
            'view_mode': 'form',
        }