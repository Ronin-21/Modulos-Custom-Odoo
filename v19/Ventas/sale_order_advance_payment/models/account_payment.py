import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de Venta',
        copy=False,
        readonly=True,
        index=True,
    )
    sale_advance_payment_id = fields.Many2one(
        'sale.order.advance.payment',
        string='Pago Adelantado de Venta',
        copy=False,
        readonly=True,
        index=True,
    )

    def write(self, vals):
        result = super().write(vals)
        # When payment state changes to cancelled, update the advance payment record
        # (Odoo 19: el estado cancelado es 'canceled', no 'cancel')
        if 'state' in vals and vals['state'] in ('canceled', 'rejected'):
            for payment in self:
                if (
                    payment.sale_advance_payment_id
                    and payment.sale_advance_payment_id.state not in ('applied', 'cancelled')
                ):
                    payment.sale_advance_payment_id.write({'state': 'cancelled'})
                    _logger.info(
                        'Pago adelantado %s marcado como cancelado porque el pago contable %s fue cancelado.',
                        payment.sale_advance_payment_id.name,
                        payment.name,
                    )
        return result

    def action_cancel(self):
        result = super().action_cancel()
        for payment in self:
            if (
                payment.sale_advance_payment_id
                and payment.sale_advance_payment_id.state not in ('applied', 'cancelled')
            ):
                payment.sale_advance_payment_id.write({'state': 'cancelled'})
        return result

    def action_draft(self):
        result = super().action_draft()
        for payment in self:
            if (
                payment.sale_advance_payment_id
                and payment.sale_advance_payment_id.state == 'posted'
            ):
                payment.sale_advance_payment_id.write({'state': 'draft'})
        return result
