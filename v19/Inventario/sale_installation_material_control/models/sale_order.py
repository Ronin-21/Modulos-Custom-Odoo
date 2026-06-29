# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_installation_order = fields.Boolean(
        string='Es instalación',
        compute='_compute_is_installation_order', store=True, readonly=False,
        help='Marca la venta como instalación. Se activa automáticamente si alguna línea tiene '
             'un producto configurado como servicio de instalación; también se puede marcar a mano.')
    installation_available = fields.Boolean(
        string='Control de instalación disponible',
        compute='_compute_installation_available',
        help='Falso en órdenes del flujo operativo (SOF): el control de materiales de instalación '
             'sólo aplica a las ventas nativas de Odoo.')
    installation_material_ids = fields.One2many(
        'sale.installation.material', 'sale_order_id', string='Controles de Materiales')
    installation_material_count = fields.Integer(
        compute='_compute_installation_material_info')
    has_installation_material_control = fields.Boolean(
        compute='_compute_installation_material_info')
    installation_material_state = fields.Selection(
        [
            ('draft', 'Borrador'),
            ('reserved', 'Reservado'),
            ('in_progress', 'En progreso'),
            ('done', 'Cerrado'),
            ('cancel', 'Cancelado'),
        ],
        string='Estado del control', compute='_compute_installation_material_state', store=True)

    # Resumen (sumas de las líneas de control)
    installation_original_total = fields.Float(
        string='Material presupuestado', compute='_compute_installation_totals',
        digits='Product Unit of Measure')
    installation_withdrawn_total = fields.Float(
        string='Retirado total', compute='_compute_installation_totals',
        digits='Product Unit of Measure')
    installation_returned_total = fields.Float(
        string='Devuelto total', compute='_compute_installation_totals',
        digits='Product Unit of Measure')
    installation_used_total = fields.Float(
        string='Usado real', compute='_compute_installation_totals',
        digits='Product Unit of Measure')
    installation_pending_total = fields.Float(
        string='Pendiente', compute='_compute_installation_totals',
        digits='Product Unit of Measure')

    def _is_sof_order(self):
        """True si la orden pertenece al flujo operativo SOF (sale_op_flow).

        Usa introspección para no acoplar el módulo a sale_op_flow: si ese módulo no está
        instalado, el campo no existe y se considera venta nativa.
        """
        self.ensure_one()
        if 'is_sof_order' in self._fields:
            return bool(self.is_sof_order)
        return False

    def _compute_installation_available(self):
        for order in self:
            order.installation_available = not order._is_sof_order()

    @api.depends('order_line.product_id.is_installation_service')
    def _compute_is_installation_order(self):
        for order in self:
            if not order.installation_available:
                order.is_installation_order = False
                continue
            order.is_installation_order = any(
                line.product_id.is_installation_service for line in order.order_line)

    @api.depends('installation_material_ids')
    def _compute_installation_material_info(self):
        for order in self:
            controls = order.installation_material_ids
            order.installation_material_count = len(controls)
            order.has_installation_material_control = bool(controls)

    @api.depends('installation_material_ids.state')
    def _compute_installation_material_state(self):
        for order in self:
            control = order.installation_material_ids[:1]
            order.installation_material_state = control.state if control else False

    @api.depends(
        'installation_material_ids.original_qty_total',
        'installation_material_ids.withdrawn_qty_total',
        'installation_material_ids.returned_qty_total',
        'installation_material_ids.used_qty_total',
        'installation_material_ids.pending_qty_total')
    def _compute_installation_totals(self):
        for order in self:
            controls = order.installation_material_ids
            order.installation_original_total = sum(controls.mapped('original_qty_total'))
            order.installation_withdrawn_total = sum(controls.mapped('withdrawn_qty_total'))
            order.installation_returned_total = sum(controls.mapped('returned_qty_total'))
            order.installation_used_total = sum(controls.mapped('used_qty_total'))
            order.installation_pending_total = sum(controls.mapped('pending_qty_total'))

    # ------------------------------------------------------------------
    def _action_confirm(self):
        res = super()._action_confirm()
        for order in self:
            if (order.installation_available and order.is_installation_order
                    and not order.installation_material_ids):
                order._create_installation_material_control()
        return res

    def _create_installation_material_control(self):
        self.ensure_one()
        material_lines = self.order_line.filtered(lambda l: l.is_installation_material)
        if not material_lines:
            return self.env['sale.installation.material']

        project = self.project_id if 'project_id' in self._fields else False
        task = material_lines.task_id[:1] if 'task_id' in material_lines._fields else False

        control = self.env['sale.installation.material'].sudo().create({
            'sale_order_id': self.id,
            'partner_id': self.partner_id.id,
            'warehouse_id': self.warehouse_id.id,
            'company_id': self.company_id.id,
            'project_id': project.id if project else False,
            'task_id': task.id if task else False,
            'responsible_user_id': self.user_id.id or self.env.user.id,
            'line_ids': [
                (0, 0, {
                    'sale_order_line_id': line.id,
                    'product_id': line.product_id.id,
                    'product_uom_id': line.product_uom_id.id,
                    'price_unit': line.price_unit,
                    'original_qty': line.product_uom_qty,
                })
                for line in material_lines
            ],
        })
        # Vincular cada línea de venta con su línea de control + guardar cantidad original.
        for c_line in control.line_ids:
            c_line.sale_order_line_id.with_context(skip_installation_guard=True).write({
                'installation_material_line_id': c_line.id,
                'installation_original_qty': c_line.original_qty,
            })
        control.action_reserve()
        return control

    # ------------------------------------------------------------------
    def action_view_installation_material(self):
        self.ensure_one()
        controls = self.installation_material_ids
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Control de Materiales'),
            'res_model': 'sale.installation.material',
            'context': {'default_sale_order_id': self.id, 'create': False},
        }
        if len(controls) == 1:
            action.update({'view_mode': 'form', 'res_id': controls.id})
        else:
            action.update({
                'view_mode': 'list,form',
                'domain': [('sale_order_id', '=', self.id)],
            })
        return action
