import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    advance_payment_id = fields.Many2one(
        'sale.order.advance.payment',
        string='Pago Adelantado',
        copy=False,
        readonly=True,
        index=True,
        help='Último pago adelantado registrado en la orden.',
    )
    advance_payment_ids = fields.One2many(
        'sale.order.advance.payment',
        'sale_order_id',
        string='Pagos Adelantados',
        copy=False,
        readonly=True,
    )
    advance_payment_allow_multiple = fields.Boolean(
        related='company_id.sale_advance_payment_allow_multiple',
        string='Permite Múltiples Anticipos',
    )
    advance_payment_count = fields.Integer(
        string='Pagos Adelantados',
        compute='_compute_advance_payment_fields',
    )
    advance_payment_amount = fields.Monetary(
        string='Pago Adelantado Recibido',
        compute='_compute_advance_payment_fields',
        currency_field='currency_id',
    )
    advance_payment_applied_amount = fields.Monetary(
        string='Pago Adelantado Aplicado',
        compute='_compute_advance_payment_fields',
        currency_field='currency_id',
    )
    advance_payment_pending_amount = fields.Monetary(
        string='Pago Adelantado Pendiente',
        compute='_compute_advance_payment_fields',
        currency_field='currency_id',
    )
    advance_payment_state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('posted', 'Pendiente de aplicar'),
            ('applied', 'Aplicado'),
            ('cancelled', 'Cancelado'),
        ],
        string='Estado del Pago Adelantado',
        compute='_compute_advance_payment_fields',
    )
    advance_payment_invoice_id = fields.Many2one(
        'account.move',
        string='Factura con Pago Aplicado',
        compute='_compute_advance_payment_fields',
    )
    advance_payment_estimated_balance = fields.Monetary(
        string='Saldo Estimado de la Orden',
        compute='_compute_advance_payment_fields',
        currency_field='currency_id',
        help='Saldo estimado = Total Orden - Pago Adelantado Pendiente',
    )
    advance_payment_visible = fields.Boolean(
        compute='_compute_advance_payment_visible',
        string='Pago Adelantado Disponible',
        help='False en pedidos del flujo operativo SOF; True en ventas nativas.',
    )

    @api.depends('state')
    def _compute_advance_payment_visible(self):
        # Duck-typing: si sale_op_flow está instalado, ocultar en pedidos SOF.
        # No crea dependencia directa — se verifica en tiempo de ejecución.
        has_sof = 'is_sof_order' in self.env['sale.order']._fields
        for order in self:
            order.advance_payment_visible = not (has_sof and order['is_sof_order'])

    @api.depends(
        'advance_payment_ids.state',
        'advance_payment_ids.amount',
        'advance_payment_ids.invoice_id',
        'advance_payment_ids.payment_ids.state',
        'amount_total',
    )
    def _compute_advance_payment_fields(self):
        for order in self:
            # Agregar todos los anticipos activos (posted/applied) de la orden.
            active = order.advance_payment_ids.filtered(lambda a: a.state in ('posted', 'applied'))
            posted = active.filtered(lambda a: a.state == 'posted')
            applied = active.filtered(lambda a: a.state == 'applied')

            order.advance_payment_count = len(active)
            order.advance_payment_amount = sum(active.mapped('amount'))
            order.advance_payment_applied_amount = sum(applied.mapped('amount'))
            order.advance_payment_pending_amount = sum(posted.mapped('amount'))
            order.advance_payment_estimated_balance = (
                order.amount_total - order.advance_payment_pending_amount
            )

            if posted:
                order.advance_payment_state = 'posted'
            elif applied:
                order.advance_payment_state = 'applied'
            else:
                order.advance_payment_state = False

            order.advance_payment_invoice_id = applied[:1].invoice_id if applied else False

    def action_register_advance_payment(self):
        self.ensure_one()
        if self.state != 'sale':
            raise UserError(_('La Orden de Venta debe estar confirmada para registrar un pago adelantado.'))
        if not self.advance_payment_allow_multiple and self.advance_payment_count > 0:
            raise UserError(_(
                'Esta orden ya tiene un pago adelantado registrado. '
                'Para permitir varios, activá "Permitir Múltiples Anticipos" en Ajustes.'
            ))
        return {
            'name': _('Registrar Pago Adelantado'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.advance.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
                'default_partner_id': self.partner_invoice_id.id or self.partner_id.id,
                'default_company_id': self.company_id.id,
                'default_currency_id': self.currency_id.id,
            },
        }

    def action_print_advance_payment_receipt(self):
        self.ensure_one()
        to_print = self.advance_payment_ids.filtered(lambda a: a.state != 'cancelled')
        if not to_print:
            raise UserError(_('No hay pago adelantado vigente para esta Orden de Venta.'))
        return self.env.ref(
            'sale_order_advance_payment.action_report_sale_advance_payment'
        ).report_action(to_print)

    def action_view_advance_payment(self):
        self.ensure_one()
        advances = self.advance_payment_ids
        if not advances:
            raise UserError(_('No hay pago adelantado registrado para esta Orden de Venta.'))
        if len(advances) == 1:
            return {
                'name': _('Pago Adelantado'),
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order.advance.payment',
                'view_mode': 'form',
                'res_id': advances.id,
            }
        return {
            'name': _('Pagos Adelantados'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.advance.payment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', advances.ids)],
        }
