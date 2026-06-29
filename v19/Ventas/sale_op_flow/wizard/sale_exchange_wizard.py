# -*- coding: utf-8 -*-
from odoo import models, fields, api, Command, _
from odoo.exceptions import UserError


class SaleExchangeWizard(models.TransientModel):
    _name = 'sale.exchange.wizard'
    _description = 'Wizard de Cambio / Devolución'

    order_id = fields.Many2one('sale.order', string='Pedido', required=True, readonly=True)
    partner_id = fields.Many2one('res.partner', related='order_id.partner_id', readonly=True)
    currency_id = fields.Many2one('res.currency', related='order_id.currency_id', readonly=True)
    company_id = fields.Many2one('res.company', related='order_id.company_id', readonly=True)
    session_id = fields.Many2one('sale.cashier.session', string='Sesión activa', readonly=True)
    reason = fields.Char(string='Motivo')

    return_line_ids = fields.One2many(
        'sale.exchange.wizard.return.line', 'wizard_id', string='Artículos que vuelven',
    )
    new_line_ids = fields.One2many(
        'sale.exchange.wizard.new.line', 'wizard_id', string='Artículos de reemplazo',
    )

    amount_return = fields.Monetary(
        compute='_compute_amounts', string='Total devuelto', currency_field='currency_id',
    )
    amount_new = fields.Monetary(
        compute='_compute_amounts', string='Total nuevo', currency_field='currency_id',
    )
    amount_difference = fields.Monetary(
        compute='_compute_amounts', string='Diferencia', currency_field='currency_id',
    )
    has_positive_diff = fields.Boolean(compute='_compute_amounts')
    has_negative_diff = fields.Boolean(compute='_compute_amounts')

    # Cobro de diferencia positiva — secciones separadas por tipo de medio
    cash_line_ids = fields.One2many(
        'sale.exchange.wizard.cash.line', 'wizard_id', string='Efectivo',
    )
    bank_line_ids = fields.One2many(
        'sale.exchange.wizard.bank.line', 'wizard_id', string='Banco / Transferencia',
    )
    amount_paid = fields.Monetary(
        compute='_compute_amounts', string='Total ingresado', currency_field='currency_id',
    )
    payment_difference = fields.Monetary(
        compute='_compute_amounts', string='Restante', currency_field='currency_id',
    )
    total_cash_change = fields.Monetary(
        compute='_compute_amounts', string='Vuelto total', currency_field='currency_id',
    )

    # Reintegro de diferencia a favor del cliente (devolución total o cambio por menor valor).
    # El cajero elige el/los medios (efectivo o banco).
    refund_line_ids = fields.One2many(
        'sale.exchange.wizard.refund.line', 'wizard_id', string='Reintegro',
    )
    original_paid_amount = fields.Monetary(
        compute='_compute_original_invoice', string='Pagado en la factura original',
        currency_field='currency_id',
    )
    amount_to_refund = fields.Monetary(
        compute='_compute_amounts', string='A reintegrar', currency_field='currency_id',
        help='Parte de la diferencia a favor del cliente que se le debe devolver en efectivo/banco '
             '(lo que efectivamente había pagado). El resto, si la venta fue a cuenta corriente, '
             'se cancela contra la deuda.',
    )
    amount_refunded = fields.Monetary(
        compute='_compute_amounts', string='Reintegrado', currency_field='currency_id',
    )
    refund_remaining = fields.Monetary(
        compute='_compute_amounts', string='Falta reintegrar', currency_field='currency_id',
    )
    has_refund = fields.Boolean(compute='_compute_amounts')

    @api.depends('order_id')
    def _compute_original_invoice(self):
        for wiz in self:
            inv = wiz.order_id.invoice_ids.filtered(
                lambda i: i.move_type == 'out_invoice' and i.state == 'posted'
            )[:1]
            wiz.original_paid_amount = (inv.amount_total - inv.amount_residual) if inv else 0.0

    @api.depends(
        'return_line_ids.subtotal', 'new_line_ids.subtotal',
        'cash_line_ids.amount', 'bank_line_ids.amount',
        'cash_line_ids.cash_received', 'refund_line_ids.amount',
        'original_paid_amount',
    )
    def _compute_amounts(self):
        for wiz in self:
            amt_return = sum(wiz.return_line_ids.mapped('subtotal'))
            amt_new = sum(wiz.new_line_ids.mapped('subtotal'))
            diff = amt_new - amt_return
            paid = sum(wiz.cash_line_ids.mapped('amount')) + sum(wiz.bank_line_ids.mapped('amount'))
            change = sum(
                max((l.cash_received or 0.0) - (l.amount or 0.0), 0.0)
                for l in wiz.cash_line_ids
            )
            wiz.amount_return = amt_return
            wiz.amount_new = amt_new
            wiz.amount_difference = diff
            wiz.has_positive_diff = diff > 0.005
            wiz.has_negative_diff = diff < -0.005
            wiz.amount_paid = paid
            wiz.payment_difference = diff - paid if diff > 0.005 else 0.0
            wiz.total_cash_change = round(change, 2) if change > 0.01 else 0.0
            # Reintegro: solo se devuelve en efectivo/banco lo que el cliente realmente pagó.
            # Lo que quedó a cuenta corriente se cancela contra la deuda (sin tocar caja).
            owed = -diff if diff < -0.005 else 0.0
            to_refund = min(owed, wiz.original_paid_amount) if owed > 0 else 0.0
            refunded = sum(wiz.refund_line_ids.mapped('amount'))
            wiz.amount_to_refund = to_refund
            wiz.amount_refunded = refunded
            wiz.refund_remaining = to_refund - refunded
            wiz.has_refund = to_refund > 0.005

    @api.model
    def _create_for_order(self, order):
        """Crea el wizard en BD antes de abrir el formulario. Es necesario para que
        default_get en cash.line/bank.line pueda leer payment_difference via default_wizard_id."""
        ctx = dict(self.env.context, default_order_id=order.id)
        self_ctx = self.with_context(ctx)
        fields_list = ['order_id', 'session_id', 'return_line_ids']
        vals = self_ctx.default_get(fields_list)
        vals['order_id'] = order.id
        return self_ctx.create(vals)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order_id = self.env.context.get('default_order_id')
        if not order_id:
            return res

        order = self.env['sale.order'].browse(order_id)
        if not order.exists():
            return res

        # Sesión abierta del cajero actual (o cualquier sesión abierta de la compañía)
        session = self.env['sale.cashier.session'].search([
            ('cashier_id', '=', self.env.uid),
            ('state', '=', 'open'),
            ('company_id', '=', order.company_id.id),
        ], limit=1)
        if not session:
            session = self.env['sale.cashier.session'].search([
                ('state', '=', 'open'),
                ('company_id', '=', order.company_id.id),
            ], limit=1)
        res['session_id'] = session.id if session else False

        # Cantidad ya devuelta por producto en cambios anteriores (para no re-devolver).
        returned_so_far = {}
        for rline in order.exchange_ids.filtered(
            lambda e: e.state == 'done'
        ).mapped('return_line_ids'):
            returned_so_far[rline.product_id.id] = \
                returned_so_far.get(rline.product_id.id, 0.0) + rline.quantity

        # Pre-cargar líneas desde la factura original, mostrando solo lo que falta devolver.
        invoice = order.invoice_ids.filtered(
            lambda i: i.move_type == 'out_invoice' and i.state == 'posted'
        )[:1]
        if invoice:
            lines = []
            for inv_line in invoice.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product' and l.product_id
            ):
                pid = inv_line.product_id.id
                consumed = min(returned_so_far.get(pid, 0.0), inv_line.quantity)
                returned_so_far[pid] = returned_so_far.get(pid, 0.0) - consumed
                returnable = inv_line.quantity - consumed
                if returnable <= 0.001:
                    continue
                lines.append((0, 0, {
                    'product_id': inv_line.product_id.id,
                    'product_uom_id': inv_line.product_uom_id.id,
                    'quantity': returnable,
                    'price_unit': inv_line.price_unit,
                    'tax_ids': [(6, 0, inv_line.tax_ids.ids)],
                    'account_id': inv_line.account_id.id,
                    'invoice_line_id': inv_line.id,
                    'quantity_returned': 0.0,
                }))
            res['return_line_ids'] = lines
        return res

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_invoice(self):
        invoice = self.order_id.invoice_ids.filtered(
            lambda i: i.move_type == 'out_invoice' and i.state == 'posted'
        )[:1]
        if not invoice:
            raise UserError(_('No hay factura confirmada para este pedido.'))
        return invoice

    def _get_outgoing_picking(self):
        return self.order_id.picking_ids.filtered(
            lambda p: p.picking_type_code == 'outgoing' and p.state == 'done'
        )[:1]

    def _get_pending_outgoing_picking(self):
        return self.order_id.picking_ids.filtered(
            lambda p: p.picking_type_code == 'outgoing' and p.state not in ('done', 'cancel')
        )[:1]

    def _auto_validate_picking(self, picking):
        """Valida el picking automáticamente forzando cantidades si es necesario (sin backorder)."""
        if not picking or picking.state == 'done':
            return
        picking.action_assign()
        for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
            move.quantity = move.product_uom_qty
        picking.with_context(
            skip_backorder=True,
            skip_sanity_check=True,
            cancel_backorder=True,
        ).button_validate()

    def _resolve_income_account(self, product):
        return (
            product.property_account_income_id
            or product.categ_id.property_account_income_categ_id
        )

    # ── Creación de documentos ────────────────────────────────────────────────

    def _create_return_picking(self):
        return_lines = self.return_line_ids.filtered(lambda l: l.quantity_returned > 0.005)
        if not return_lines:
            return False

        original_picking = self._get_outgoing_picking()
        order = self.order_id
        warehouse = order.warehouse_id or self.env['stock.warehouse'].search(
            [('company_id', '=', order.company_id.id)], limit=1
        )
        in_type = warehouse.in_type_id
        location_src = (
            order.partner_id.property_stock_customer
            or self.env.ref('stock.stock_location_customers', raise_if_not_found=False)
        )
        location_dest = in_type.default_location_dest_id or warehouse.lot_stock_id

        picking_vals = {
            'picking_type_id': in_type.id,
            'partner_id': order.partner_id.id,
            'origin': _('Devolución de %s') % order.name,
            'location_id': location_src.id if location_src else False,
            'location_dest_id': location_dest.id,
            'company_id': order.company_id.id,
        }
        if original_picking:
            picking_vals['return_id'] = original_picking.id

        new_picking = self.env['stock.picking'].create(picking_vals)
        for rline in return_lines:
            orig_move = (
                original_picking.move_ids.filtered(
                    lambda m, p=rline.product_id: m.product_id == p and m.state == 'done'
                )[:1]
                if original_picking else False
            )
            move_vals = {
                'description_picking': rline.product_id.display_name,
                'product_id': rline.product_id.id,
                'product_uom_qty': rline.quantity_returned,
                'product_uom': rline.product_uom_id.id or rline.product_id.uom_id.id,
                'picking_id': new_picking.id,
                'location_id': picking_vals['location_id'],
                'location_dest_id': picking_vals['location_dest_id'],
                'picking_type_id': in_type.id,
            }
            if orig_move:
                move_vals['origin_returned_move_id'] = orig_move.id
            self.env['stock.move'].create(move_vals)

        new_picking.action_confirm()
        new_picking.action_assign()
        return new_picking

    def _create_new_delivery_picking(self):
        new_lines = self.new_line_ids.filtered(lambda l: l.quantity > 0.005)
        if not new_lines:
            return False

        order = self.order_id
        warehouse = order.warehouse_id or self.env['stock.warehouse'].search(
            [('company_id', '=', order.company_id.id)], limit=1
        )
        out_type = warehouse.out_type_id
        location_src = out_type.default_location_src_id or warehouse.lot_stock_id
        location_dest = (
            order.partner_id.property_stock_customer
            or self.env.ref('stock.stock_location_customers', raise_if_not_found=False)
        )

        new_picking = self.env['stock.picking'].create({
            'picking_type_id': out_type.id,
            'partner_id': order.partner_id.id,
            'origin': _('Reemplazo de %s') % order.name,
            'location_id': location_src.id,
            'location_dest_id': location_dest.id if location_dest else False,
            'company_id': order.company_id.id,
        })
        for nline in new_lines:
            self.env['stock.move'].create({
                'description_picking': nline.product_id.display_name,
                'product_id': nline.product_id.id,
                'product_uom_qty': nline.quantity,
                'product_uom': nline.product_uom_id.id or nline.product_id.uom_id.id,
                'picking_id': new_picking.id,
                'location_id': location_src.id,
                'location_dest_id': location_dest.id if location_dest else False,
                'picking_type_id': out_type.id,
            })
        new_picking.action_confirm()
        new_picking.action_assign()
        return new_picking

    def _create_credit_note(self, original_invoice):
        return_lines = self.return_line_ids.filtered(lambda l: l.quantity_returned > 0.005)
        if not return_lines:
            return False

        nc_lines = []
        for rline in return_lines:
            account = rline.account_id or self._resolve_income_account(rline.product_id)
            nc_lines.append(Command.create({
                'product_id': rline.product_id.id,
                'name': rline.product_id.display_name,
                'quantity': rline.quantity_returned,
                'price_unit': rline.price_unit,
                'product_uom_id': rline.product_uom_id.id or rline.product_id.uom_id.id,
                'tax_ids': [(6, 0, rline.tax_ids.ids)],
                'account_id': account.id if account else False,
            }))

        credit_note = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': self.order_id.partner_id.id,
            'invoice_origin': self.order_id.name,
            'ref': _('Devolución de %s — %s') % (original_invoice.name, self.reason),
            'company_id': self.order_id.company_id.id,
            'currency_id': self.order_id.currency_id.id,
            'journal_id': original_invoice.journal_id.id,
            'invoice_line_ids': nc_lines,
        })
        credit_note.action_post()
        return credit_note

    def _create_new_invoice(self, original_invoice):
        new_lines_data = self.new_line_ids.filtered(lambda l: l.quantity > 0.005)
        if not new_lines_data:
            return False

        inv_lines = []
        for nline in new_lines_data:
            account = nline.account_id or self._resolve_income_account(nline.product_id)
            inv_lines.append(Command.create({
                'product_id': nline.product_id.id,
                'name': nline.product_id.display_name,
                'quantity': nline.quantity,
                'price_unit': nline.price_unit,
                'product_uom_id': nline.product_uom_id.id or nline.product_id.uom_id.id,
                'tax_ids': [(6, 0, nline.tax_ids.ids)],
                'account_id': account.id if account else False,
            }))

        new_invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.order_id.partner_id.id,
            'invoice_origin': self.order_id.name,
            'ref': _('Reemplazo en cambio de %s') % self.order_id.name,
            'company_id': self.order_id.company_id.id,
            'currency_id': self.order_id.currency_id.id,
            'journal_id': original_invoice.journal_id.id,
            'invoice_line_ids': inv_lines,
        })
        new_invoice.action_post()
        return new_invoice

    def _reconcile_nc_with_new_invoice(self, credit_note, new_invoice):
        """Aplica la NC contra la nueva factura para netear el saldo pendiente."""
        nc_lines = credit_note.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
        )
        inv_lines = new_invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
        )
        if nc_lines and inv_lines:
            (nc_lines + inv_lines).reconcile()

    def _register_difference_payments(self, invoice):
        """Registra los pagos de la diferencia positiva contra la nueva factura."""
        all_lines = list(self.cash_line_ids.filtered(lambda l: l.amount > 0.005)) + \
                    list(self.bank_line_ids.filtered(lambda l: l.amount > 0.005))
        for pline in all_lines:
            ref_parts = [_('Cobro diferencia cambio %s') % self.order_id.name]
            if hasattr(pline, 'voucher_number') and pline.voucher_number:
                ref_parts.append(_('Comprobante: %s') % pline.voucher_number)
            if hasattr(pline, 'coupon_number') and pline.coupon_number:
                ref_parts.append(_('Cupón: %s') % pline.coupon_number)
            payment = self.env['account.payment'].create({
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': self.order_id.partner_id.id,
                'amount': pline.amount,
                'journal_id': pline.journal_id.id,
                'currency_id': self.order_id.currency_id.id,
                'memo': ' | '.join(ref_parts),
                'op_cashier_session_id': self.session_id.id if self.session_id else False,
                'op_sale_order_id': self.order_id.id,
                'op_coupon_number': getattr(pline, 'coupon_number', False) or False,
            })
            payment.action_post()
            # Reconciliar contra el saldo restante de la nueva factura
            (invoice.line_ids + payment.move_id.line_ids).filtered(
                lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
            ).reconcile()

    def _reconcile_nc_with_original(self, credit_note, original_invoice):
        """Aplica la NC contra el saldo abierto de la factura original (cancela deuda
        en cuenta corriente). Si la factura ya estaba pagada, no hay saldo y no concilia nada."""
        nc_lines = credit_note.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
        )
        inv_lines = original_invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
        )
        if nc_lines and inv_lines:
            (nc_lines + inv_lines).reconcile()

    def _register_refund_payments(self, credit_note):
        """Registra el reintegro al cliente (egreso de caja) y lo concilia con la NC."""
        for pline in self.refund_line_ids.filtered(lambda l: l.amount > 0.005):
            ref_parts = [_('Reintegro por devolución %s') % self.order_id.name]
            if pline.voucher_number:
                ref_parts.append(_('Comprobante: %s') % pline.voucher_number)
            payment = self.env['account.payment'].create({
                'payment_type': 'outbound',
                'partner_type': 'customer',
                'partner_id': self.order_id.partner_id.id,
                'amount': pline.amount,
                'journal_id': pline.journal_id.id,
                'currency_id': self.order_id.currency_id.id,
                'memo': ' | '.join(ref_parts),
                'op_cashier_session_id': self.session_id.id if self.session_id else False,
                'op_sale_order_id': self.order_id.id,
            })
            payment.action_post()
            # Reconciliar el egreso contra la NC para saldarla
            (credit_note.line_ids + payment.move_id.line_ids).filtered(
                lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
            ).reconcile()

    # ── Confirmación ──────────────────────────────────────────────────────────

    def action_confirm(self):
        self.ensure_one()
        order = self.order_id

        if not self.reason or not self.reason.strip():
            raise UserError(_('El campo Motivo es obligatorio.'))

        # Validar cantidades de devolución
        for line in self.return_line_ids:
            if line.quantity_returned < 0:
                raise UserError(_('La cantidad a devolver no puede ser negativa.'))
            if line.product_id and line.quantity_returned > line.quantity:
                raise UserError(_(
                    'No podés devolver más de lo facturado (%s unidades de %s).'
                ) % (line.quantity, line.product_id.display_name))

        has_returns = any(l.quantity_returned > 0.005 for l in self.return_line_ids)
        has_new = any(l.quantity > 0.005 for l in self.new_line_ids)
        if not has_returns and not has_new:
            raise UserError(_('Debés especificar al menos un artículo a devolver o uno de reemplazo.'))

        if self.has_positive_diff:
            if not self.session_id or self.session_id.state != 'open':
                raise UserError(_('Se requiere una sesión de caja abierta para cobrar la diferencia.'))
            diff = order.currency_id.round(self.amount_difference)
            paid = order.currency_id.round(self.amount_paid)
            if abs(diff - paid) > 0.01:
                raise UserError(_(
                    'El total ingresado ($%.2f) no coincide con la diferencia a cobrar ($%.2f).'
                ) % (paid, diff))

        if self.has_refund:
            if not self.session_id or self.session_id.state != 'open':
                raise UserError(_('Se requiere una sesión de caja abierta para reintegrar al cliente.'))
            to_refund = order.currency_id.round(self.amount_to_refund)
            refunded = order.currency_id.round(self.amount_refunded)
            if abs(to_refund - refunded) > 0.01:
                raise UserError(_(
                    'El reintegro cargado ($%.2f) no coincide con el monto a devolver ($%.2f).'
                ) % (refunded, to_refund))

        invoice = self._get_invoice()

        # ── Lógica de pickings según estado de la entrega original ───────────
        # Caso 1: entrega original NO validada → cancelarla; no se devuelve stock
        # Caso 2: entrega original YA validada → devolución + nueva entrega auto-validadas
        original_done = self._get_outgoing_picking()       # state == 'done'
        original_pending = self._get_pending_outgoing_picking()  # confirmado pero no validado

        if original_pending:
            # Caso 1: cancelar entrega pendiente; los artículos nunca salieron
            original_pending.action_cancel()
            return_picking = False
        else:
            # Caso 2: crear devolución y validarla automáticamente
            return_picking = self._create_return_picking() if has_returns else False
            if return_picking:
                self._auto_validate_picking(return_picking)

        new_picking = self._create_new_delivery_picking() if has_new else False
        if new_picking and original_done:
            # Caso 2: auto-validar también la nueva entrega
            self._auto_validate_picking(new_picking)
        # Caso 1: la nueva entrega queda en cola para despacho

        credit_note = self._create_credit_note(invoice) if has_returns else False
        new_invoice = self._create_new_invoice(invoice) if has_new else False

        # Netear NC contra nueva factura cuando coexisten
        if credit_note and new_invoice:
            self._reconcile_nc_with_new_invoice(credit_note, new_invoice)

        # Cobrar diferencia positiva
        if self.has_positive_diff and new_invoice:
            self._register_difference_payments(new_invoice)

        # Diferencia a favor del cliente (devolución total o cambio por menor valor):
        # 1) cancelar deuda en cuenta corriente conciliando la NC contra la factura original;
        # 2) reintegrar en efectivo/banco lo que el cliente realmente había pagado.
        if self.has_negative_diff and credit_note:
            self._reconcile_nc_with_original(credit_note, invoice)
            if self.has_refund:
                self._register_refund_payments(credit_note)

        exchange = self.env['sale.exchange'].create({
            'order_id': order.id,
            'session_id': self.session_id.id if self.session_id else False,
            'reason': self.reason,
            'state': 'done',
            'credit_note_id': credit_note.id if credit_note else False,
            'new_invoice_id': new_invoice.id if new_invoice else False,
            'return_picking_id': return_picking.id if return_picking else False,
            'new_picking_id': new_picking.id if new_picking else False,
            'supplement_paid': bool(self.has_positive_diff),
            'return_line_ids': [
                (0, 0, {
                    'product_id': l.product_id.id,
                    'product_uom_id': l.product_uom_id.id,
                    'quantity': l.quantity_returned,
                    'price_unit': l.price_unit,
                    'tax_ids': [(6, 0, l.tax_ids.ids)],
                    'account_id': l.account_id.id if l.account_id else False,
                })
                for l in self.return_line_ids.filtered(lambda l: l.quantity_returned > 0.005)
            ],
            'new_line_ids': [
                (0, 0, {
                    'product_id': l.product_id.id,
                    'product_uom_id': l.product_uom_id.id,
                    'quantity': l.quantity,
                    'price_unit': l.price_unit,
                    'tax_ids': [(6, 0, l.tax_ids.ids)],
                    'account_id': l.account_id.id if l.account_id else False,
                })
                for l in self.new_line_ids.filtered(lambda l: l.quantity > 0.005)
            ],
        })

        order.message_post(body=_(
            'Cambio/Devolución registrado por <b>%s</b>. Motivo: %s'
        ) % (self.env.user.name, self.reason))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.exchange',
            'res_id': exchange.id,
            'view_mode': 'form',
            'target': 'current',
        }


class SaleExchangeWizardReturnLine(models.TransientModel):
    _name = 'sale.exchange.wizard.return.line'
    _description = 'Línea devuelta (Wizard de Cambio)'

    wizard_id = fields.Many2one('sale.exchange.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id')
    invoice_line_id = fields.Many2one('account.move.line', string='Línea original', readonly=True)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unidad', readonly=True)
    quantity = fields.Float(string='Facturado', readonly=True)
    quantity_returned = fields.Float(string='Devuelve', default=0.0)
    price_unit = fields.Float(string='Precio unit.', readonly=True, digits='Product Price')
    tax_ids = fields.Many2many('account.tax', string='Impuestos', readonly=True)
    account_id = fields.Many2one('account.account', string='Cuenta', readonly=True)
    subtotal = fields.Monetary(
        string='Subtotal', compute='_compute_subtotal', currency_field='currency_id',
    )

    @api.depends('quantity_returned', 'price_unit', 'tax_ids')
    def _compute_subtotal(self):
        for line in self:
            if line.quantity_returned > 0:
                taxes = line.tax_ids.compute_all(line.price_unit, quantity=line.quantity_returned)
                line.subtotal = taxes['total_included']
            else:
                line.subtotal = 0.0

    # Validación movida a action_confirm para evitar dispararse en líneas vacías transient


class SaleExchangeWizardNewLine(models.TransientModel):
    _name = 'sale.exchange.wizard.new.line'
    _description = 'Línea de reemplazo (Wizard de Cambio)'

    wizard_id = fields.Many2one('sale.exchange.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id')
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unidad')
    quantity = fields.Float(string='Cantidad', default=1.0)
    price_unit = fields.Float(string='Precio unit.', digits='Product Price')
    tax_ids = fields.Many2many('account.tax', string='Impuestos')
    account_id = fields.Many2one('account.account', string='Cuenta')
    subtotal = fields.Monetary(
        string='Subtotal', compute='_compute_subtotal', currency_field='currency_id',
    )

    @api.depends('quantity', 'price_unit', 'tax_ids')
    def _compute_subtotal(self):
        for line in self:
            taxes = line.tax_ids.compute_all(line.price_unit, quantity=line.quantity)
            line.subtotal = taxes['total_included']

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if not self.product_id:
            return
        self.product_uom_id = self.product_id.uom_id
        self.price_unit = self.product_id.lst_price
        order = self.wizard_id.order_id
        self.tax_ids = self.product_id.taxes_id.filtered(
            lambda t: t.company_id == order.company_id
        )
        self.account_id = (
            self.product_id.property_account_income_id
            or self.product_id.categ_id.property_account_income_categ_id
        )


class SaleExchangeWizardCashLine(models.TransientModel):
    _name = 'sale.exchange.wizard.cash.line'
    _description = 'Línea de efectivo (Wizard de Cambio)'

    wizard_id = fields.Many2one('sale.exchange.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id')
    company_id = fields.Many2one('res.company', related='wizard_id.company_id')
    journal_id = fields.Many2one(
        'account.journal', string='Caja',
        domain="[('type', '=', 'cash')]",
        required=True,
    )
    amount = fields.Monetary(string='A cobrar', currency_field='currency_id')
    cash_received = fields.Monetary(string='Recibido', currency_field='currency_id')
    cash_change = fields.Monetary(
        string='Vuelto', compute='_compute_cash_change', currency_field='currency_id',
    )

    @api.depends('cash_received', 'amount')
    def _compute_cash_change(self):
        for line in self:
            excess = (line.cash_received or 0.0) - (line.amount or 0.0)
            line.cash_change = excess if excess > 0.01 else 0.0

    @api.onchange('amount')
    def _onchange_amount(self):
        if not self.cash_received or self.cash_received < self.amount:
            self.cash_received = self.amount


class SaleExchangeWizardBankLine(models.TransientModel):
    _name = 'sale.exchange.wizard.bank.line'
    _description = 'Línea de banco/transferencia (Wizard de Cambio)'

    wizard_id = fields.Many2one('sale.exchange.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id')
    company_id = fields.Many2one('res.company', related='wizard_id.company_id')
    journal_id = fields.Many2one(
        'account.journal', string='Medio de pago',
        domain="[('type', '=', 'bank')]",
        required=True,
    )
    amount = fields.Monetary(string='Monto', currency_field='currency_id')
    voucher_number = fields.Char(string='Nº Comprobante')
    coupon_number = fields.Char(string='Nº Cupón')


class SaleExchangeWizardRefundLine(models.TransientModel):
    _name = 'sale.exchange.wizard.refund.line'
    _description = 'Línea de reintegro al cliente (Wizard de Cambio)'

    wizard_id = fields.Many2one('sale.exchange.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id')
    company_id = fields.Many2one('res.company', related='wizard_id.company_id')
    journal_id = fields.Many2one(
        'account.journal', string='Medio de reintegro',
        domain="[('type', 'in', ['cash', 'bank']), ('company_id', '=', company_id)]",
        required=True,
    )
    amount = fields.Monetary(string='Monto', currency_field='currency_id')
    voucher_number = fields.Char(string='Nº Comprobante')

