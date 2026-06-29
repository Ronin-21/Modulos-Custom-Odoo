from odoo import _, models

PARAM_WARN_REFUND = 'sale_invoice_delivery_control.warn_refund_on_delivered_goods'

MSG_BLOCK = (
    "No se puede crear esta nota de crédito porque existe mercadería entregada "
    "que aún no fue devuelta.\n\n"
    "Para emitir una nota de crédito debe registrar primero la devolución de "
    "la mercadería en Inventario. El sistema calculará automáticamente las "
    "cantidades acreditables según lo efectivamente devuelto."
)


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    def _sidc_enabled(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            PARAM_WARN_REFUND, default='True'
        ) == 'True'

    def _sidc_check_and_get_net(self):
        """
        Retorna ('skip'|'block'|'adjust', payload, stock_pids).
        """
        if not self._sidc_enabled():
            return 'skip', None, None
        if self.env.context.get('skip_delivery_refund_warning'):
            return 'skip', None, None

        combined_net = {}
        combined_stock_pids = set()
        has_any_delivery = False
        summary_lines = []

        for move in self.move_ids:
            if move.move_type != 'out_invoice':
                continue
            sale_orders = move._sidc_get_related_sale_orders()
            if not sale_orders:
                continue

            net, stock_pids = move._sidc_calculate_net_returnable(sale_orders)
            if net is None:
                continue

            has_any_delivery = True
            combined_stock_pids |= stock_pids

            for order in sale_orders:
                done = order.picking_ids.filtered(
                    lambda p: p.picking_type_code == 'outgoing' and p.state == 'done'
                )
                if done:
                    summary_lines.append('Orden {} → {}'.format(
                        order.name, ', '.join(done.mapped('name'))
                    ))

            for pid, qty in net.items():
                combined_net[pid] = combined_net.get(pid, 0.0) + qty

        if not has_any_delivery:
            return 'skip', None, None
        if not combined_net:
            return 'block', '\n'.join(summary_lines), None
        return 'adjust', combined_net, combined_stock_pids

    def reverse_moves(self, *args, **kwargs):
        action, payload, stock_pids = self._sidc_check_and_get_net()

        if action == 'skip':
            return super().reverse_moves(*args, **kwargs)

        if action == 'block':
            wizard = self.env['refund.delivery.warning.wizard'].create({
                'message': _(MSG_BLOCK),
                'delivery_summary': payload or '',
            })
            return {
                'name': _('No se puede crear la nota de crédito'),
                'type': 'ir.actions.act_window',
                'res_model': 'refund.delivery.warning.wizard',
                'res_id': wizard.id,
                'view_mode': 'form',
                'target': 'new',
            }

        # action == 'adjust'
        net_returnable = payload
        original_invoice_ids = self.move_ids.filtered(
            lambda m: m.move_type == 'out_invoice'
        ).ids

        # Marcar el ID máximo ANTES de crear la NC para luego ubicarla
        # con certeza sin depender de self.new_move_ids ni del resultado.
        last_move = self.env['account.move'].search(
            [], order='id desc', limit=1
        )
        max_id_before = last_move.id if last_move else 0

        result = super(
            AccountMoveReversal,
            self.with_context(skip_delivery_refund_warning=True),
        ).reverse_moves(*args, **kwargs)

        # Buscar las NCs creadas después del marcador, sin depender
        # de caché ni de self.new_move_ids.
        new_refunds = self.env['account.move'].search([
            ('id', '>', max_id_before),
            ('move_type', '=', 'out_refund'),
            ('reversed_entry_id', 'in', original_invoice_ids),
        ])

        for refund in new_refunds:
            refund._sidc_adjust_refund_lines(net_returnable, stock_pids)
            orders = (
                refund.reversed_entry_id._sidc_get_related_sale_orders()
                if refund.reversed_entry_id
                else refund._sidc_get_related_sale_orders()
            )
            refund._sidc_log_chatter_adjusted(orders, net_returnable)

        return result
