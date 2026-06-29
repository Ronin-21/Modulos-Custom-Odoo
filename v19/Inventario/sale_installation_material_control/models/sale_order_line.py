# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

ADMIN_GROUP = 'sale_installation_material_control.group_installation_admin'


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_installation_material = fields.Boolean(
        string='Material de instalación', compute='_compute_is_installation_material',
        store=True)
    installation_material_line_id = fields.Many2one(
        'sale.installation.material.line', string='Línea de control', copy=False,
        readonly=True, ondelete='set null')

    # Trazabilidad (se conservan aunque se ajuste product_uom_qty al cerrar)
    installation_original_qty = fields.Float(
        string='Cant. presupuestada (instalación)', copy=False, readonly=True,
        digits='Product Unit of Measure')
    installation_withdrawn_qty = fields.Float(
        string='Retirado', copy=False, readonly=True, digits='Product Unit of Measure')
    installation_returned_qty = fields.Float(
        string='Devuelto', copy=False, readonly=True, digits='Product Unit of Measure')
    installation_used_qty = fields.Float(
        string='Usado real', copy=False, readonly=True, digits='Product Unit of Measure')
    installation_released_qty = fields.Float(
        string='Liberado', copy=False, readonly=True, digits='Product Unit of Measure')

    @api.depends(
        'order_id.is_installation_order', 'product_id.type', 'product_id.is_storable',
        'display_type')
    def _compute_is_installation_material(self):
        for line in self:
            line.is_installation_material = bool(
                line.order_id.is_installation_order
                and not line.display_type
                and line.product_id
                and line.product_id.type == 'consu'
                and line.product_id.is_storable)

    # ------------------------------------------------------------------
    # Suprimir el procurement nativo para las líneas de material: el módulo
    # gestiona todos sus movimientos con sus propios pickings.
    # ------------------------------------------------------------------
    def _action_launch_stock_rule(self, *, previous_product_uom_qty=False):
        lines = self.filtered(lambda l: not l.is_installation_material)
        if not lines:
            return True
        return super(SaleOrderLine, lines)._action_launch_stock_rule(
            previous_product_uom_qty=previous_product_uom_qty)

    # ------------------------------------------------------------------
    # Facturación: nada facturable hasta cerrar; luego sólo lo usado.
    # ------------------------------------------------------------------
    @api.depends(
        'installation_material_line_id.installation_id.state',
        'installation_material_line_id.used_qty')
    def _compute_qty_to_invoice(self):
        super()._compute_qty_to_invoice()
        for line in self:
            c_line = line.installation_material_line_id
            if line.is_installation_material and c_line:
                if c_line.installation_id.state != 'done':
                    line.qty_to_invoice = 0.0
                else:
                    line.qty_to_invoice = c_line.used_qty - line.qty_invoiced

    @api.depends('installation_material_line_id.installation_id.state')
    def _compute_invoice_status(self):
        super()._compute_invoice_status()
        for line in self:
            c_line = line.installation_material_line_id
            if line.is_installation_material and c_line \
                    and c_line.installation_id.state != 'done':
                line.invoice_status = 'no'

    # ------------------------------------------------------------------
    def write(self, vals):
        if 'product_uom_qty' in vals and not self.env.context.get('skip_installation_guard'):
            is_admin = self.env.user.has_group(ADMIN_GROUP)
            for line in self:
                c_line = line.installation_material_line_id
                if (line.is_installation_material and c_line
                        and c_line.installation_id.state == 'done' and not is_admin):
                    raise UserError(_(
                        'No se puede modificar la cantidad de un material de instalación ya '
                        'cerrado (%s). Reabrí el control o pedí a un administrador.')
                        % line.product_id.display_name)
        return super().write(vals)
