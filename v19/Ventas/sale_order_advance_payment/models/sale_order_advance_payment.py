import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaleOrderAdvancePayment(models.Model):
    _name = 'sale.order.advance.payment'
    _description = 'Pago Adelantado de Orden de Venta'
    _order = 'payment_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Referencia',
        readonly=True,
        copy=False,
        index=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de Venta',
        required=True,
        ondelete='restrict',
        readonly=True,
        index=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        required=True,
        readonly=True,
    )
    amount = fields.Monetary(
        string='Importe',
        currency_field='currency_id',
        required=True,
        readonly=True,
    )
    payment_date = fields.Date(
        string='Fecha de Pago',
        required=True,
        readonly=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario',
        readonly=True,
        help='Diario del pago principal. En cobro múltiple, el del primer pago.',
    )
    payment_method_line_id = fields.Many2one(
        'account.payment.method.line',
        string='Método de Pago',
        readonly=True,
    )
    payment_id = fields.Many2one(
        'account.payment',
        string='Pago Contable Principal',
        readonly=True,
        copy=False,
        ondelete='restrict',
    )
    payment_ids = fields.One2many(
        'account.payment',
        'sale_advance_payment_id',
        string='Pagos Contables',
        readonly=True,
    )
    payment_count = fields.Integer(
        string='Cantidad de Pagos',
        compute='_compute_payment_count',
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Factura Aplicada',
        readonly=True,
        copy=False,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('posted', 'Publicado'),
            ('applied', 'Aplicado'),
            ('cancelled', 'Cancelado'),
        ],
        string='Estado',
        default='draft',
        readonly=True,
        copy=False,
        index=True,
    )
    reference = fields.Char(string='Referencia Interna')
    note = fields.Text(string='Notas')

    # Related / computed
    payment_state = fields.Selection(
        related='payment_id.state',
        string='Estado del Pago Contable',
        readonly=True,
    )
    sale_order_amount_total = fields.Monetary(
        related='sale_order_id.amount_total',
        string='Total Orden de Venta',
        currency_field='currency_id',
        readonly=True,
    )
    create_uid = fields.Many2one(
        'res.users',
        string='Registrado por',
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') and vals.get('sale_order_id'):
                sale_order = self.env['sale.order'].browse(vals['sale_order_id'])
                existing = self.search_count([('sale_order_id', '=', sale_order.id)])
                vals['name'] = '%s-%02d' % (sale_order.name, existing + 1)
        return super().create(vals_list)

    @api.depends('payment_ids')
    def _compute_payment_count(self):
        for rec in self:
            rec.payment_count = len(rec.payment_ids)

    def name_get(self):
        result = []
        for rec in self:
            name = rec.name or _('Pago Adelantado #%d') % rec.id
            result.append((rec.id, name))
        return result

    def action_view_payment(self):
        self.ensure_one()
        payments = self.payment_ids or self.payment_id
        if not payments:
            raise UserError(_('No hay pago contable asociado a este registro.'))
        if len(payments) == 1:
            return {
                'name': _('Pago Contable'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment',
                'view_mode': 'form',
                'res_id': payments.id,
            }
        return {
            'name': _('Pagos Contables'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', payments.ids)],
        }

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_('No hay factura aplicada a este pago adelantado.'))
        return {
            'name': _('Factura Aplicada'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.invoice_id.id,
        }
