# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaleDispatchWizard(models.TransientModel):
    _name = 'sale.dispatch.wizard'
    _description = 'Wizard de Despacho'

    sale_order_id = fields.Many2one('sale.order', string='Pedido', required=True, readonly=True)
    partner_id = fields.Many2one(
        'res.partner', string='Cliente',
        related='sale_order_id.partner_id', readonly=True,
    )
    line_ids = fields.One2many('sale.dispatch.wizard.line', 'wizard_id', string='Productos')
    delivery_mode = fields.Selection(
        [('pickup', 'Retiro en local'), ('delivery', 'Reparto con flete')],
        string='Modalidad de entrega',
        default='pickup',
        required=True,
    )
    delivery_date = fields.Date(string='Fecha de entrega', default=fields.Date.today)
    delivery_shift = fields.Selection(
        [('morning', 'Mañana'), ('afternoon', 'Tarde')],
        string='Turno',
    )
    notes = fields.Text(string='Notas de despacho')
    has_lines = fields.Boolean(compute='_compute_has_lines')

    @api.depends('line_ids')
    def _compute_has_lines(self):
        for wiz in self:
            wiz.has_lines = bool(wiz.line_ids)

    @api.model
    def _create_for_order(self, order):
        """Crea el wizard y sus líneas server-side para evitar que move_id
        (required) quede ausente en el payload del formulario Odoo 19."""
        pending_pickings = order.picking_ids.filtered(
            lambda p: p.picking_type_code == 'outgoing' and p.state not in ('done', 'cancel')
        )

        for picking in pending_pickings:
            if picking.state in ('draft', 'waiting', 'confirmed'):
                picking.sudo().action_confirm()
            if picking.state in ('waiting', 'confirmed', 'partially_available'):
                picking.sudo().action_assign()
            picking.invalidate_recordset(['state'])

        line_vals = []
        for picking in pending_pickings:
            for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                line_vals.append((0, 0, {
                    'move_id': move.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'qty_ordered': move.product_uom_qty,
                    'qty_to_dispatch': move.product_uom_qty,
                }))

        return self.create({
            'sale_order_id': order.id,
            'line_ids': line_vals,
        })

    def action_confirm(self):
        self.ensure_one()
        order = self.sale_order_id

        if not self.line_ids:
            # Orden de servicio sin picking físico
            self._finalize_dispatch(order)
            return self._reload_order(order)

        total_to_dispatch = sum(l.qty_to_dispatch for l in self.line_ids)
        if total_to_dispatch <= 0:
            raise UserError(_('Ingresá al menos una cantidad mayor a cero para despachar.'))

        pickings_to_validate = self.env['stock.picking']
        for line in self.line_ids:
            qty = line.qty_to_dispatch or 0.0
            move = line.move_id
            picking = move.picking_id

            if qty <= 0:
                move.sudo().quantity = 0.0
            else:
                if move.state != 'assigned' and order._sof_allow_dispatch_without_stock():
                    move.sudo()._set_quantity_done(qty)
                    move.sudo().write({'picked': True})
                    move.sudo().move_line_ids.write({'picked': True})
                else:
                    move.sudo().quantity = qty
                pickings_to_validate |= picking

        for picking in pickings_to_validate:
            picking.sudo().with_context(
                cancel_backorder=False,
                sof_skip_auto_mark_dispatched=True,
                skip_sanity_check=True,
            )._action_done()

        order._sof_invalidate_pickings_cache()
        all_outgoing = order.picking_ids.filtered(
            lambda p: p.picking_type_code == 'outgoing' and p.state != 'cancel'
        )
        all_done = all(p.state == 'done' for p in all_outgoing)

        if all_done:
            self._finalize_dispatch(order)
        else:
            dispatched_lines = self.line_ids.filtered(lambda l: l.qty_to_dispatch > 0)
            detail = ', '.join(
                '%s: %.2f %s' % (l.product_id.display_name, l.qty_to_dispatch, l.product_uom_id.name)
                for l in dispatched_lines
            )
            order.message_post(
                body=_('📦 Despacho parcial por <b>%s</b>.<br/>%s') % (self.env.user.name, detail)
            )
            if self.notes:
                order.write({'dispatch_notes': self.notes})

        return self._reload_order(order)

    def _finalize_dispatch(self, order):
        if self.delivery_mode == 'delivery':
            order._mark_as_in_delivery(
                notes=self.notes,
                delivery_date=self.delivery_date,
                delivery_shift=self.delivery_shift,
            )
        else:
            order._mark_as_dispatched()
            if self.notes:
                order.write({'dispatch_notes': self.notes})

    def _reload_order(self, order):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': order.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }


class SaleDispatchWizardLine(models.TransientModel):
    _name = 'sale.dispatch.wizard.line'
    _description = 'Línea de despacho'
    _order = 'id'

    wizard_id = fields.Many2one('sale.dispatch.wizard', required=True, ondelete='cascade')
    move_id = fields.Many2one('stock.move', string='Movimiento', required=True, readonly=True)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unidad', readonly=True)
    qty_ordered = fields.Float(
        string='Demanda', readonly=True, digits='Product Unit of Measure',
    )
    qty_to_dispatch = fields.Float(
        string='A despachar ahora', digits='Product Unit of Measure',
    )

    @api.constrains('qty_to_dispatch', 'qty_ordered')
    def _check_qty(self):
        for line in self:
            if line.qty_to_dispatch < 0:
                raise UserError(_('La cantidad a despachar no puede ser negativa.'))
            if line.qty_to_dispatch > line.qty_ordered:
                raise UserError(_(
                    'La cantidad a despachar (%.2f) supera la demanda (%.2f) para "%s".'
                ) % (line.qty_to_dispatch, line.qty_ordered, line.product_id.display_name))
