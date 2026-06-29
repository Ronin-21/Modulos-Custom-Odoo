from markupsafe import Markup
from odoo import _, fields, models

PARAM_WARN_REFUND = 'sale_invoice_delivery_control.warn_refund_on_delivered_goods'

MSG_BLOCK = (
    "No se puede crear esta nota de crédito porque existe mercadería entregada "
    "que aún no fue devuelta.\n\n"
    "Para emitir una nota de crédito debe registrar primero la devolución de "
    "la mercadería en Inventario. El sistema calculará automáticamente las "
    "cantidades acreditables según lo efectivamente devuelto."
)


class AccountMove(models.Model):
    _inherit = 'account.move'

    sidc_lines_locked = fields.Boolean(
        string='Líneas bloqueadas por ajuste de devolución',
        default=False,
        copy=False,
        help='Indica que las líneas de esta NC fueron ajustadas automáticamente '
             'por el módulo de control factura-entrega. Las líneas no son editables.',
    )

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------

    def _sidc_warn_refund_enabled(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            PARAM_WARN_REFUND, default='True'
        ) == 'True'

    # ------------------------------------------------------------------
    # Detección de órdenes de venta
    # ------------------------------------------------------------------

    def _sidc_get_related_sale_orders(self):
        orders = self.env['sale.order']
        for line in self.invoice_line_ids:
            for sl in getattr(line, 'sale_line_ids', []):
                orders |= sl.order_id
        if not orders and self.invoice_origin:
            orders = self.env['sale.order'].search(
                [('name', '=', self.invoice_origin)]
            )
        if not orders:
            orders = self.env['sale.order'].search(
                [('invoice_ids', 'in', self.ids)]
            )
        return orders

    # ------------------------------------------------------------------
    # Detección de stock
    # NO filtramos por product.type porque en Odoo 18 los almacenables
    # tienen type='consu' y is_storable=True — difiere entre builds.
    # Criterio: si un producto generó un stock.move done, se rastrea.
    # ------------------------------------------------------------------

    def _sidc_get_outgoing_data(self, sale_orders):
        """
        Devuelve (set_move_ids, {product_id: qty_total_salida}).
        Incluye todos los movimientos done de pickings de salida.
        """
        move_ids = set()
        qty_by_product = {}
        for order in sale_orders:
            for picking in order.picking_ids:
                if picking.picking_type_code != 'outgoing':
                    continue
                if picking.state != 'done':
                    continue
                for move in picking.move_ids:
                    if move.state != 'done':
                        continue
                    qty = move.quantity or move.product_qty or 0.0
                    if qty <= 0:
                        continue
                    move_ids.add(move.id)
                    pid = move.product_id.id
                    qty_by_product[pid] = qty_by_product.get(pid, 0.0) + qty
        return move_ids, qty_by_product

    def _sidc_get_returned_qty_by_stock(self, sale_orders, outgoing_move_ids):
        """
        Devuelve {product_id: qty} devuelta via pickings de entrada
        vinculados a salidas de la orden.
        """
        returned = {}
        for order in sale_orders:
            for picking in order.picking_ids:
                if picking.picking_type_code != 'incoming':
                    continue
                if picking.state != 'done':
                    continue
                for move in picking.move_ids:
                    if move.state != 'done':
                        continue
                    if not move.origin_returned_move_id:
                        continue
                    if move.origin_returned_move_id.id not in outgoing_move_ids:
                        continue
                    qty = move.quantity or move.product_qty or 0.0
                    if qty <= 0:
                        continue
                    pid = move.product_id.id
                    returned[pid] = returned.get(pid, 0.0) + qty
        return returned

    def _sidc_get_already_credited_qty(self, sale_orders, exclude_move_id=None):
        """
        Devuelve {product_id: qty} ya acreditada en NCs posted de la orden.
        """
        credited = {}
        for order in sale_orders:
            for inv in order.invoice_ids:
                if inv.move_type != 'out_refund' or inv.state != 'posted':
                    continue
                if exclude_move_id and inv.id == exclude_move_id:
                    continue
                for line in inv.invoice_line_ids:
                    if line.display_type != 'product' or not line.product_id:
                        continue
                    pid = line.product_id.id
                    credited[pid] = credited.get(pid, 0.0) + (line.quantity or 0.0)
        return credited

    def _sidc_calculate_net_returnable(self, sale_orders, exclude_move_id=None):
        """
        Retorna:
          (None, set())       → sin pickings de salida done
          ({}, {pids})        → pickings done pero sin devoluciones de stock
          ({pid:qty}, {pids}) → hay saldo; pids = productos con salida done
        """
        outgoing_ids, outgoing_by_product = self._sidc_get_outgoing_data(sale_orders)
        if not outgoing_ids:
            return None, set()

        returned = self._sidc_get_returned_qty_by_stock(sale_orders, outgoing_ids)
        if not returned:
            return {}, set(outgoing_by_product.keys())

        credited = self._sidc_get_already_credited_qty(sale_orders, exclude_move_id)

        net = {}
        for pid, qty_ret in returned.items():
            net_qty = qty_ret - credited.get(pid, 0.0)
            if net_qty > 0.001:
                net[pid] = net_qty

        return net, set(outgoing_by_product.keys())

    # ------------------------------------------------------------------
    # Ajuste de líneas
    # ------------------------------------------------------------------

    def _sidc_adjust_refund_lines(self, net_returnable, stock_pids=None):
        """
        Ajusta líneas de la NC usando write() con check_move_validity=False
        para garantizar persistencia en Odoo 18.

        - Producto en net_returnable → ajustar cantidad con write()
        - Producto en stock_pids pero no en net_returnable → eliminar línea
        - Producto no en stock_pids → no tocar (servicio)
        """
        ctx = dict(self.env.context, check_move_validity=False)
        lines_to_unlink = self.env['account.move.line']

        for line in self.with_context(ctx).invoice_line_ids:
            if line.display_type != 'product' or not line.product_id:
                continue
            pid = line.product_id.id
            is_stock_line = (
                pid in net_returnable
                or (stock_pids is not None and pid in stock_pids)
            )
            if not is_stock_line:
                continue

            if pid not in net_returnable:
                lines_to_unlink |= line
            else:
                qty_base = net_returnable[pid]
                product_uom = line.product_id.uom_id
                line_uom = line.product_uom_id
                if line_uom and product_uom and line_uom.id != product_uom.id:
                    try:
                        qty = product_uom._compute_quantity(qty_base, line_uom)
                    except Exception:
                        qty = qty_base
                else:
                    qty = qty_base
                line.with_context(ctx).write({'quantity': qty})

        if lines_to_unlink:
            lines_to_unlink.with_context(ctx).unlink()

        # Marcar la NC como bloqueada (líneas no editables por el usuario)
        self.sudo().write({'sidc_lines_locked': True})
        # Forzar flush para que los cambios queden en DB antes de retornar
        self.env['account.move.line'].flush_model(['quantity'])

    # ------------------------------------------------------------------
    # Chatter (Markup para que el HTML se renderice correctamente)
    # ------------------------------------------------------------------

    def _sidc_log_chatter_adjusted(self, sale_orders, net_returnable):
        originals = self.mapped('reversed_entry_id')
        if not originals and sale_orders:
            originals = self.env['account.move'].search([
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('id', 'in', sale_orders.mapped('invoice_ids').ids),
            ])
        items = Markup('').join(
            Markup('<li>{}: {}</li>').format(
                self.env['product.product'].browse(pid).display_name,
                round(qty, 4),
            )
            for pid, qty in net_returnable.items()
        )
        body = Markup(
            "📦 <b>Nota de crédito generada con cantidades ajustadas a las devoluciones.</b><br/>"
            "Cantidades calculadas: devuelto por stock menos NCs anteriores ya publicadas."
            "<ul>{items}</ul>"
        ).format(items=items)
        for inv in originals:
            inv.message_post(body=body)

    # ------------------------------------------------------------------
    # Helpers legacy
    # ------------------------------------------------------------------

    def _sidc_has_delivered_storable_goods(self, sale_orders):
        move_ids, _ = self._sidc_get_outgoing_data(sale_orders)
        return bool(move_ids)

    def _sidc_refund_has_storable_lines(self):
        return self.move_type == 'out_refund'

    def _sidc_build_delivery_summary(self, sale_orders):
        lines = []
        for order in sale_orders:
            done = order.picking_ids.filtered(
                lambda p: p.picking_type_code == 'outgoing' and p.state == 'done'
            )
            if done:
                lines.append('Orden {} → {}'.format(
                    order.name, ', '.join(done.mapped('name'))
                ))
        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # Override action_post (publicación manual de NC en borrador)
    # ------------------------------------------------------------------

    def action_post(self):
        if self.env.context.get('skip_delivery_refund_warning'):
            return super().action_post()

        refunds = self.filtered(lambda m: m.move_type == 'out_refund')

        # Cambio mínimo:
        # Si no hay notas de crédito de cliente, este módulo no debe intervenir.
        # Esto deja pasar normalmente facturas de proveedor, facturas de cliente,
        # notas de crédito de proveedor y asientos contables.
        if not refunds:
            return super().action_post()

        if not self._sidc_warn_refund_enabled():
            return super().action_post()

        other = self - refunds
        if other:
            super(AccountMove, other).action_post()

        for refund in refunds:
            original = refund.reversed_entry_id or refund
            sale_orders = original._sidc_get_related_sale_orders()
            if not sale_orders:
                super(AccountMove, refund).action_post()
                continue

            net, stock_pids = refund._sidc_calculate_net_returnable(
                sale_orders, exclude_move_id=refund.id
            )
            if net is None:
                super(AccountMove, refund).action_post()
                continue

            if not net:
                wizard = self.env['refund.delivery.warning.wizard'].create({
                    'message': _(MSG_BLOCK),
                    'delivery_summary': refund._sidc_build_delivery_summary(sale_orders),
                })
                return {
                    'name': _('No se puede confirmar la nota de crédito'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'refund.delivery.warning.wizard',
                    'res_id': wizard.id,
                    'view_mode': 'form',
                    'target': 'new',
                }

            refund._sidc_adjust_refund_lines(net, stock_pids)
            super(AccountMove, refund).action_post()
            refund._sidc_log_chatter_adjusted(sale_orders, net)

        return True
