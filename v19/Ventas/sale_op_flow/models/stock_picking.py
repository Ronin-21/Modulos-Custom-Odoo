# -*- coding: utf-8 -*-
"""
stock.picking — Control de despacho v2

Lógica:
- El operario de DESPACHO puede VER y PREPARAR el pedido desde que está 'confirmed'
  (el picking ya existe y está en estado ready/assigned)
- Solo puede VALIDAR la entrega cuando la factura del pedido está pagada
  (payment_state in ['paid', 'in_payment'])
- Después de validar → marca el pedido como 'dispatched'

No bloqueamos la preparación (pick/pack), solo la validación final (done).
"""
from odoo import models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        """
        Override: verifica que la factura esté pagada antes de permitir
        la validación de la entrega.
        Solo aplica a pickings de salida (outgoing) con sale_id.
        """
        for picking in self:
            sale_order = getattr(picking, 'sale_id', False)
            if not sale_order or picking.picking_type_code != 'outgoing':
                continue

            op_state = getattr(sale_order, 'operational_state', False)
            if not op_state:
                continue  # Módulo no activo para este pedido

            # Si ya fue despachado, no bloquear (podría ser una devolución o corrección)
            if op_state == 'dispatched':
                continue

            # Si está cancelado, bloquear siempre
            if op_state == 'cancelled':
                raise UserError(
                    _('El pedido "%s" está cancelado. No se puede validar la entrega.')
                    % sale_order.name
                )

            # Las ventas en CC tienen la factura pendiente por diseño — se permite despachar
            if getattr(sale_order, 'is_credit_sale', False):
                continue

            # Verificar que la factura esté pagada
            if not sale_order._is_invoice_paid():
                raise UserError(
                    _('⚠️ No se puede entregar el pedido "%s".\n\n'
                      'La factura aún NO está pagada.\n\n'
                      'El cliente debe presentar su comprobante de pago antes '
                      'de que puedas validar la entrega.\n\n'
                      'Estado del pedido: %s')
                    % (sale_order.name, dict([
                        ('quotation', 'Presupuesto'),
                        ('confirmed', 'Confirmado — pendiente de pago'),
                        ('paid', 'Pagado'),
                        ('dispatched', 'Despachado'),
                        ('cancelled', 'Cancelado'),
                    ]).get(op_state, op_state))
                )

        # Validación estándar de Odoo
        result = super().button_validate()

        # Post-validación: marcar pedido como despachado.
        # Cuando la validación se dispara desde el botón propio de Despacho en
        # sale.order, esa acción marca el pedido con el usuario operativo real.
        if not self.env.context.get('sof_skip_auto_mark_dispatched'):
            for picking in self:
                sale_order = getattr(picking, 'sale_id', False)
                if not sale_order or picking.picking_type_code != 'outgoing':
                    continue
                if picking.state == 'done':
                    all_out = sale_order.picking_ids.filtered(
                        lambda p: p.picking_type_code == 'outgoing'
                    )
                    if all(p.state == 'done' for p in all_out):
                        sale_order._mark_as_dispatched()

        return result
