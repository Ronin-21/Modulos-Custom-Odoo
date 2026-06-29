# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_round

# Mapa de tipos de movimiento interno del flujo de instalación.
#   key -> (campo de ubicación origen, campo de ubicación destino, campo del tipo de operación)
# Las ubicaciones especiales 'lot_stock' y 'customer' se resuelven aparte.
INSTALLATION_MOVE_TYPES = ['reserve', 'withdraw', 'return', 'consume', 'release']


class SaleInstallationMaterial(models.Model):
    _name = 'sale.installation.material'
    _description = 'Control de Materiales de Instalación'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Referencia', required=True, copy=False, readonly=True,
        default=lambda self: _('Nuevo'),
    )
    sale_order_id = fields.Many2one(
        'sale.order', string='Orden de Venta', required=True, readonly=True,
        ondelete='cascade', index=True,
    )
    project_id = fields.Many2one('project.project', string='Proyecto', readonly=True)
    task_id = fields.Many2one('project.task', string='Tarea', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén', required=True, readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id', readonly=True)
    responsible_user_id = fields.Many2one(
        'res.users', string='Responsable',
        default=lambda self: self.env.user, tracking=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Borrador'),
            ('reserved', 'Reservado'),
            ('in_progress', 'En progreso'),
            ('done', 'Cerrado'),
            ('cancel', 'Cancelado'),
        ],
        string='Estado', default='draft', required=True, tracking=True, copy=False,
    )
    date_start = fields.Datetime(string='Inicio', readonly=True, copy=False)
    date_done = fields.Datetime(string='Cierre', readonly=True, copy=False)
    notes = fields.Text(string='Observaciones')

    line_ids = fields.One2many(
        'sale.installation.material.line', 'installation_id', string='Materiales',
    )
    picking_ids = fields.One2many('stock.picking', 'installation_id', string='Movimientos')
    picking_count = fields.Integer(compute='_compute_picking_counts')
    withdrawal_picking_count = fields.Integer(compute='_compute_picking_counts')
    return_picking_count = fields.Integer(compute='_compute_picking_counts')
    release_picking_count = fields.Integer(compute='_compute_picking_counts')

    # Totales (para resumen / kanban / pivot)
    original_qty_total = fields.Float(
        string='Presupuestado', compute='_compute_qty_totals', store=True,
        digits='Product Unit of Measure')
    withdrawn_qty_total = fields.Float(
        string='Retirado', compute='_compute_qty_totals', store=True,
        digits='Product Unit of Measure')
    returned_qty_total = fields.Float(
        string='Devuelto', compute='_compute_qty_totals', store=True,
        digits='Product Unit of Measure')
    used_qty_total = fields.Float(
        string='Usado', compute='_compute_qty_totals', store=True,
        digits='Product Unit of Measure')
    pending_qty_total = fields.Float(
        string='Pendiente', compute='_compute_qty_totals', store=True,
        digits='Product Unit of Measure')
    in_installer_qty_total = fields.Float(
        string='En poder del instalador', compute='_compute_qty_totals', store=True,
        digits='Product Unit of Measure')
    reserved_qty_total = fields.Float(
        string='Reservado', compute='_compute_qty_totals',
        digits='Product Unit of Measure')
    can_reserve = fields.Boolean(compute='_compute_can_reserve')

    _sql_constraints = [
        ('sale_order_uniq', 'unique(sale_order_id)',
         'Ya existe un control de materiales para esta orden de venta.'),
    ]

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('picking_ids', 'picking_ids.installation_move_type', 'picking_ids.state')
    def _compute_picking_counts(self):
        for rec in self:
            pickings = rec.picking_ids.filtered(lambda p: p.state != 'cancel')
            rec.picking_count = len(pickings)
            rec.withdrawal_picking_count = len(
                pickings.filtered(lambda p: p.installation_move_type == 'withdraw'))
            rec.return_picking_count = len(
                pickings.filtered(lambda p: p.installation_move_type == 'return'))
            rec.release_picking_count = len(
                pickings.filtered(lambda p: p.installation_move_type == 'release'))

    @api.depends(
        'line_ids.original_qty', 'line_ids.withdrawn_qty', 'line_ids.returned_qty',
        'line_ids.used_qty', 'line_ids.pending_qty', 'line_ids.in_installer_qty',
        'line_ids.reserved_qty')
    def _compute_qty_totals(self):
        for rec in self:
            rec.original_qty_total = sum(rec.line_ids.mapped('original_qty'))
            rec.withdrawn_qty_total = sum(rec.line_ids.mapped('withdrawn_qty'))
            rec.returned_qty_total = sum(rec.line_ids.mapped('returned_qty'))
            rec.used_qty_total = sum(rec.line_ids.mapped('used_qty'))
            rec.pending_qty_total = sum(rec.line_ids.mapped('pending_qty'))
            rec.in_installer_qty_total = sum(rec.line_ids.mapped('in_installer_qty'))
            rec.reserved_qty_total = sum(rec.line_ids.mapped('reserved_qty'))

    @api.depends('state', 'line_ids.original_qty', 'line_ids.reserved_qty')
    def _compute_can_reserve(self):
        for rec in self:
            pending = sum(l.original_qty - l.reserved_qty for l in rec.line_ids)
            rec.can_reserve = rec.state in ('draft', 'reserved') and pending > 0.0001

    # ------------------------------------------------------------------
    # Helpers de stock
    # ------------------------------------------------------------------
    def _get_customer_location(self):
        self.ensure_one()
        partner = self.sale_order_id.partner_shipping_id or self.partner_id
        location = partner.with_company(self.company_id).property_stock_customer
        if not location:
            location = self.env.ref('stock.stock_location_customers', raise_if_not_found=False)
        if not location:
            raise UserError(_('No se pudo determinar la ubicación de cliente para el consumo.'))
        return location

    def _get_move_locations(self, move_type):
        """Devuelve (origen, destino, tipo_operación) para un tipo de movimiento."""
        self.ensure_one()
        wh = self.warehouse_id.with_company(self.company_id)
        wh._setup_installation_material_control()  # idempotente
        reserved = wh.installation_reserved_loc_id
        installer = wh.installation_installer_loc_id
        lot_stock = wh.lot_stock_id
        customer = self._get_customer_location()
        mapping = {
            'reserve': (lot_stock, reserved, wh.installation_reserve_type_id),
            'withdraw': (reserved, installer, wh.installation_withdraw_type_id),
            'return': (installer, reserved, wh.installation_return_type_id),
            'consume': (installer, customer, wh.installation_consume_type_id),
            'release': (reserved, lot_stock, wh.installation_release_type_id),
        }
        if move_type not in mapping:
            raise UserError(_('Tipo de movimiento de instalación desconocido: %s') % move_type)
        return mapping[move_type]

    def _run_internal_move(self, line, qty, move_type, responsible=False):
        """Crea, confirma y valida un picking de un único movimiento de instalación.

        Devuelve el picking creado (o un recordset vacío si qty <= 0).
        Para 'reserve' se topea la cantidad al stock libre disponible (no fuerza negativo).
        """
        self.ensure_one()
        product = line.product_id
        rounding = line.product_uom_id.rounding
        qty = float_round(qty, precision_rounding=rounding)
        if float_compare(qty, 0.0, precision_rounding=rounding) <= 0:
            return self.env['stock.picking']

        src, dest, ptype = self._get_move_locations(move_type)
        if not ptype or not src or not dest:
            raise UserError(_(
                'Faltan ubicaciones o tipos de operación de instalación en el almacén "%s". '
                'Configurálos en Inventario > Configuración.') % self.warehouse_id.display_name)

        if move_type == 'reserve':
            available = product.sudo().with_company(self.company_id).with_context(
                location=src.id, warehouse=self.warehouse_id.id).free_qty
            available = float_round(max(available, 0.0), precision_rounding=rounding)
            if float_compare(available, qty, precision_rounding=rounding) < 0:
                self.message_post(body=_(
                    'Stock insuficiente para reservar %(req)s de %(prod)s. '
                    'Se reservó %(av)s.',
                    req=qty, prod=product.display_name, av=available))
                qty = available
            if float_compare(qty, 0.0, precision_rounding=rounding) <= 0:
                return self.env['stock.picking']

        picking = self.env['stock.picking'].sudo().create({
            'picking_type_id': ptype.id,
            'location_id': src.id,
            'location_dest_id': dest.id,
            'origin': self.name,
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'installation_id': self.id,
            'installation_move_type': move_type,
            'installation_responsible_id': (responsible or self.responsible_user_id).id,
        })
        move_vals = {
            'name': product.display_name,
            'product_id': product.id,
            'product_uom_qty': qty,
            'product_uom': line.product_uom_id.id,
            'location_id': src.id,
            'location_dest_id': dest.id,
            'picking_id': picking.id,
            'company_id': self.company_id.id,
            'installation_line_id': line.id,
            'installation_move_type': move_type,
        }
        if move_type == 'consume':
            # Sólo el consumo final impacta qty_delivered / facturación de la venta.
            move_vals['sale_line_id'] = line.sale_order_line_id.id
        move = self.env['stock.move'].sudo().create(move_vals)

        picking.action_confirm()
        picking.action_assign()
        move.quantity = qty
        move.picked = True
        picking.with_context(
            cancel_backorder=True, skip_backorder=True, skip_sanity_check=True
        )._action_done()
        return picking

    # ------------------------------------------------------------------
    # Acciones de estado
    # ------------------------------------------------------------------
    def action_reserve(self):
        for rec in self:
            if rec.state not in ('draft', 'reserved'):
                raise UserError(_('Sólo se puede reservar un control en borrador.'))
            for line in rec.line_ids:
                pending_to_reserve = line.original_qty - line.reserved_qty
                rec._run_internal_move(line, pending_to_reserve, 'reserve')
            rec.write({'state': 'reserved', 'date_start': fields.Datetime.now()})
        return True

    def _set_in_progress(self):
        for rec in self:
            if rec.state == 'reserved':
                rec.state = 'in_progress'

    def action_open_close_wizard(self):
        self.ensure_one()
        self._check_can_close()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cerrar consumo de materiales'),
            'res_model': 'installation.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_installation_id': self.id},
        }

    def action_open_withdrawal_wizard(self):
        self.ensure_one()
        self._check_operational()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Crear retiro'),
            'res_model': 'installation.withdrawal.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_installation_id': self.id},
        }

    def action_open_return_wizard(self):
        self.ensure_one()
        self._check_operational()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Registrar devolución'),
            'res_model': 'installation.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_installation_id': self.id},
        }

    def _check_operational(self):
        self.ensure_one()
        if self.state not in ('reserved', 'in_progress'):
            raise UserError(_(
                'No se pueden registrar movimientos: el control está en estado "%s".')
                % dict(self._fields['state'].selection).get(self.state))
        if not self.env.user._can_validate_installation_material():
            raise UserError(_(
                'No tenés permiso para operar retiros/devoluciones de instalación.'))

    def _check_can_close(self):
        self.ensure_one()
        if self.state not in ('reserved', 'in_progress'):
            raise UserError(_('Sólo se puede cerrar un control reservado o en progreso.'))
        if not self.env.user.has_group(
                'sale_installation_material_control.group_installation_admin'):
            raise UserError(_('Sólo un administrador de instalación puede cerrar el control.'))
        pending = self.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel'))
        if pending:
            raise UserError(_(
                'Hay movimientos pendientes de validar (%s). Validalos o cancelalos antes '
                'de cerrar.') % ', '.join(pending.mapped('name')))

    def _do_close(self, adjust_so_qty=True):
        """Ejecuta el cierre: consumo, liberación y ajuste de la venta. Lo llama el wizard."""
        self.ensure_one()
        self._check_can_close()
        for line in self.line_ids:
            used = line.used_qty
            surplus = line.original_qty - used
            rounding = line.product_uom_id.rounding
            # 1) Consumo final del material en poder del instalador -> cliente.
            if float_compare(line.in_installer_qty, 0.0, precision_rounding=rounding) > 0:
                self._run_internal_move(line, line.in_installer_qty, 'consume')
            # 2) Liberación del sobrante reservado -> stock libre.
            if float_compare(surplus, 0.0, precision_rounding=rounding) > 0:
                self._run_internal_move(line, surplus, 'release')
            # 3) Trazabilidad + ajuste de la línea de venta.
            so_line = line.sale_order_line_id
            so_vals = {
                'installation_used_qty': used,
                'installation_withdrawn_qty': line.withdrawn_qty,
                'installation_returned_qty': line.returned_qty,
                'installation_released_qty': max(surplus, 0.0),
            }
            if adjust_so_qty and so_line:
                so_vals['product_uom_qty'] = used
            if so_line:
                so_line.with_context(skip_installation_guard=True).write(so_vals)
        self.write({'state': 'done', 'date_done': fields.Datetime.now()})
        self.sale_order_id._compute_installation_material_state()
        return True

    def action_reopen(self):
        for rec in self:
            if rec.state != 'done':
                raise UserError(_('Sólo se puede reabrir un control cerrado.'))
            if not self.env.user.has_group(
                    'sale_installation_material_control.group_installation_admin'):
                raise UserError(_('Sólo un administrador puede reabrir un control.'))
            invoiced = rec.line_ids.filtered(
                lambda l: l.sale_order_line_id and l.sale_order_line_id.qty_invoiced > 0)
            if invoiced:
                raise UserError(_(
                    'No se puede reabrir: la venta ya tiene cantidades facturadas. '
                    'Revertí la factura primero.'))
            rec.state = 'in_progress'
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state == 'done':
                raise UserError(_('No se puede cancelar un control cerrado; usá Reabrir.'))
            rec.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel')).action_cancel()
            rec.state = 'cancel'
        return True

    def action_draft(self):
        for rec in self:
            if rec.state == 'cancel':
                rec.state = 'draft'
        return True

    # ------------------------------------------------------------------
    # Smart buttons
    # ------------------------------------------------------------------
    def action_view_pickings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Movimientos de instalación'),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('installation_id', '=', self.id)],
            'context': {'create': False},
        }

    def action_view_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sale.installation.material') or _('Nuevo')
        return super().create(vals_list)
