import logging
from odoo import models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_TRANSIT_LOCATION_NAME = 'Tránsito Inter-Sucursal'


class StockInterbranchTransferLine(models.TransientModel):
    _name = 'stock.interbranch.transfer.line'
    _description = 'Línea de Transferencia Inter-Sucursal'

    wizard_id = fields.Many2one(
        'stock.interbranch.transfer.wizard', required=True, ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product', string='Producto', required=True,
        domain=[('is_storable', '=', True)],
    )
    quantity = fields.Float(string='Cantidad', required=True, default=1.0, digits='Product Unit of Measure')
    uom_id = fields.Many2one('uom.uom', string='Unidad', related='product_id.uom_id', readonly=True)


class StockInterbranchTransferWizard(models.TransientModel):
    _name = 'stock.interbranch.transfer.wizard'
    _description = 'Transferencia Inter-Sucursal'

    warehouse_src_id = fields.Many2one(
        'stock.warehouse', string='Sucursal Origen', required=True,
    )
    warehouse_dst_id = fields.Many2one(
        'stock.warehouse', string='Sucursal Destino', required=True,
        domain="[('id', '!=', warehouse_src_id)]",
    )
    line_ids = fields.One2many(
        'stock.interbranch.transfer.line', 'wizard_id', string='Productos',
    )
    state = fields.Selection([('draft', 'Borrador'), ('done', 'Creado')], default='draft')
    picking_src_id = fields.Many2one('stock.picking', string='Transferencia Salida', readonly=True)
    picking_dst_id = fields.Many2one('stock.picking', string='Transferencia Entrada', readonly=True)

    # ── Helpers ──────────────────────────────────────────────────────────────────

    def _get_or_create_transit_location(self):
        Location = self.env['stock.location'].sudo()
        transit = Location.search([
            ('name', '=', _TRANSIT_LOCATION_NAME),
            ('usage', '=', 'transit'),
            ('active', '=', True),
        ], limit=1)
        if not transit:
            parent = Location.search([
                ('complete_name', 'ilike', 'Virtual'),
                ('usage', '=', 'view'),
            ], limit=1)
            transit = Location.create({
                'name': _TRANSIT_LOCATION_NAME,
                'usage': 'transit',
                'location_id': parent.id if parent else False,
                'active': True,
                'company_id': False,
            })
            _logger.info('SPLB: Ubicación de tránsito inter-sucursal creada (id=%s)', transit.id)
        return transit

    def _get_internal_picking_type(self, warehouse):
        return self.env['stock.picking.type'].sudo().search([
            ('warehouse_id', '=', warehouse.id),
            ('code', '=', 'internal'),
        ], limit=1)

    def _find_splb_location(self, product, warehouse):
        config = self.env['stock.product.branch.location'].sudo().search([
            ('product_id', '=', product.id),
            ('warehouse_id', '=', warehouse.id),
            ('company_id', '=', warehouse.company_id.id),
            ('active', '=', True),
        ], limit=1)
        if config and config.location_id and config.location_id.active:
            return config.location_id
        return warehouse.lot_stock_id

    # ── Acción principal ─────────────────────────────────────────────────────────

    def action_create_transfers(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Agregue al menos un producto.'))
        if self.warehouse_src_id == self.warehouse_dst_id:
            raise UserError(_('La sucursal origen y destino deben ser distintas.'))

        wh_src = self.warehouse_src_id
        wh_dst = self.warehouse_dst_id
        company_src = wh_src.company_id
        company_dst = wh_dst.company_id

        pt_src = self._get_internal_picking_type(wh_src)
        pt_dst = self._get_internal_picking_type(wh_dst)
        if not pt_src:
            raise UserError(_('No se encontró operación interna para "%s".') % wh_src.name)
        if not pt_dst:
            raise UserError(_('No se encontró operación interna para "%s".') % wh_dst.name)

        transit = self._get_or_create_transit_location()

        moves_src = []
        moves_dst = []
        for line in self.line_ids:
            src_loc = self._find_splb_location(line.product_id, wh_src)
            dst_loc = self._find_splb_location(line.product_id, wh_dst)
            moves_src.append((0, 0, {
                'product_id': line.product_id.id,
                'product_uom': line.product_id.uom_id.id,
                'product_uom_qty': line.quantity,
                'location_id': src_loc.id,
                'location_dest_id': transit.id,
                'company_id': company_src.id,
            }))
            moves_dst.append((0, 0, {
                'product_id': line.product_id.id,
                'product_uom': line.product_id.uom_id.id,
                'product_uom_qty': line.quantity,
                'location_id': transit.id,
                'location_dest_id': dst_loc.id,
                'company_id': company_dst.id,
            }))

        Picking = self.env['stock.picking'].sudo()

        picking_src = Picking.with_company(company_src).create({
            'picking_type_id': pt_src.id,
            'location_id': wh_src.lot_stock_id.id,
            'location_dest_id': transit.id,
            'company_id': company_src.id,
            'move_ids': moves_src,
            'origin': _('Inter-Sucursal → %s') % wh_dst.name,
            # Las ubicaciones ya están calculadas por el wizard; evitar que el hook
            # de auto-ubicación las sobreescriba o bloquee por falta de configuración.
            'splb_disable_auto': True,
        })

        picking_dst = Picking.with_company(company_dst).create({
            'picking_type_id': pt_dst.id,
            'location_id': transit.id,
            'location_dest_id': wh_dst.lot_stock_id.id,
            'company_id': company_dst.id,
            'move_ids': moves_dst,
            'origin': _('Inter-Sucursal ← %s [%s]') % (wh_src.name, picking_src.name),
            'splb_disable_auto': True,
        })

        # Actualizar el origen cruzado ahora que ambos tienen nombre
        picking_src.write({
            'origin': _('Inter-Sucursal → %s [%s]') % (wh_dst.name, picking_dst.name),
        })
        picking_dst.write({
            'origin': _('Inter-Sucursal ← %s [%s]') % (wh_src.name, picking_src.name),
        })

        # Confirmar ambos albaranes para que aparezcan en el panel de cada sucursal
        # y sean visibles en la lista de "Por hacer" de cada almacén.
        picking_src.action_confirm()
        picking_dst.action_confirm()

        self.write({
            'state': 'done',
            'picking_src_id': picking_src.id,
            'picking_dst_id': picking_dst.id,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_src_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': self.picking_src_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_dst_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': self.picking_dst_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
