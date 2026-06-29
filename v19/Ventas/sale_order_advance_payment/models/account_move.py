import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    sale_advance_payment_id = fields.Many2one(
        'sale.order.advance.payment',
        string='Pago Adelantado Aplicado',
        copy=False,
        readonly=True,
        index=True,
    )
    sale_advance_payment_amount = fields.Monetary(
        string='Importe Pago Adelantado',
        copy=False,
        readonly=True,
        currency_field='currency_id',
    )
    sale_advance_payment_origin = fields.Char(
        string='Referencia Pago Adelantado',
        copy=False,
        readonly=True,
    )
    sale_advance_payment_note = fields.Char(
        string='Leyenda Pago Adelantado',
        copy=False,
        readonly=True,
    )

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        customer_invoices = self.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'posted'
        )
        if customer_invoices:
            customer_invoices._apply_sale_order_advance_payment()
        return posted

    def _apply_sale_order_advance_payment(self):
        """
        Aplica los pagos adelantados de la orden de venta a esta factura.
        Se llama al publicar la factura. Aplica todos los anticipos pendientes
        de la(s) orden(es) asociada(s).
        """
        for move in self:
            if move.move_type != 'out_invoice' or move.state != 'posted':
                continue

            # Find related sale orders via invoice lines → sale lines → sale order
            sale_orders = move.invoice_line_ids.sale_line_ids.order_id
            if not sale_orders and move.invoice_origin:
                # Fallback: try via invoice_origin matching sale order name
                sale_orders = self.env['sale.order'].search([
                    ('name', '=', move.invoice_origin),
                    ('company_id', '=', move.company_id.id),
                ], limit=1)

            if not sale_orders:
                continue

            applied = self.env['sale.order.advance.payment']
            for sale_order in sale_orders:
                pending = sale_order.advance_payment_ids.filtered(
                    lambda a: a.state == 'posted' and not a.invoice_id
                )
                for advance in pending:
                    if move._apply_one_advance(advance):
                        applied |= advance

            if applied:
                total = sum(applied.mapped('amount'))
                symbol = move.currency_id.symbol or ''
                move.write({
                    'sale_advance_payment_id': (move.sale_advance_payment_id.id or applied[:1].id),
                    'sale_advance_payment_amount': (move.sale_advance_payment_amount or 0.0) + total,
                    'sale_advance_payment_origin': ', '.join(applied.mapped('name')),
                    'sale_advance_payment_note': _(
                        'Pago(s) adelantado(s) aplicado(s): %s — Total %s %s',
                        ', '.join(applied.mapped('name')),
                        symbol,
                        '%.2f' % total,
                    ),
                })

    def _apply_one_advance(self, advance):
        """Reconcilia un anticipo concreto con esta factura. Devuelve True si se aplicó."""
        self.ensure_one()
        move = self

        # Recolectar todos los pagos activos de la ficha (cobro único o múltiple)
        payments = advance.payment_ids or advance.payment_id
        active_payments = payments.filtered(
            lambda p: p.state not in ('canceled', 'rejected', 'draft')
        )
        if not active_payments:
            return False

        # Validar coincidencia de empresa, moneda y cliente
        if advance.company_id != move.company_id:
            _logger.warning('Pago adelantado %s: empresa no coincide con factura %s.', advance.name, move.name)
            return False
        if advance.currency_id != move.currency_id:
            _logger.warning('Pago adelantado %s: moneda no coincide con factura %s.', advance.name, move.name)
            return False
        if move.partner_id.commercial_partner_id != advance.partner_id.commercial_partner_id:
            _logger.warning('Pago adelantado %s: cliente no coincide con factura %s.', advance.name, move.name)
            return False

        payment_receivable_lines = active_payments.move_id.line_ids.filtered(
            lambda l: (
                l.account_id.account_type == 'asset_receivable'
                and not l.reconciled
                and l.amount_residual != 0
            )
        )
        invoice_receivable_lines = move.line_ids.filtered(
            lambda l: (
                l.account_id.account_type == 'asset_receivable'
                and not l.reconciled
                and l.amount_residual != 0
            )
        )
        if not payment_receivable_lines or not invoice_receivable_lines:
            _logger.warning(
                'Pago adelantado %s: no se encontraron líneas conciliables para la factura %s.',
                advance.name, move.name,
            )
            return False

        # Conciliar por cuenta: reconcile() exige apuntes de la misma cuenta.
        all_lines = payment_receivable_lines | invoice_receivable_lines
        common_accounts = (
            payment_receivable_lines.mapped('account_id')
            & invoice_receivable_lines.mapped('account_id')
        )
        accounts_to_process = common_accounts or all_lines.mapped('account_id')

        try:
            for account in accounts_to_process:
                account_lines = all_lines.filtered(
                    lambda l, acc=account: l.account_id == acc and not l.reconciled
                )
                if len(account_lines) > 1:
                    account_lines.reconcile()
            advance.write({'state': 'applied', 'invoice_id': move.id})
            _logger.info('Pago adelantado %s aplicado correctamente a la factura %s.', advance.name, move.name)
            return True
        except Exception:
            _logger.exception('Error al aplicar el pago adelantado %s a la factura %s.', advance.name, move.name)
            return False
