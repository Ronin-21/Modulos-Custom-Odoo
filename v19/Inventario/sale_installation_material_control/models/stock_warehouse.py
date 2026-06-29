# -*- coding: utf-8 -*-
from odoo import fields, models, _


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    installation_reserved_loc_id = fields.Many2one(
        'stock.location', string='Ubicación Reservado Instalaciones', copy=False)
    installation_installer_loc_id = fields.Many2one(
        'stock.location', string='Ubicación En Poder del Instalador', copy=False)

    installation_reserve_type_id = fields.Many2one(
        'stock.picking.type', string='Tipo de operación: Reserva', copy=False)
    installation_withdraw_type_id = fields.Many2one(
        'stock.picking.type', string='Tipo de operación: Retiro', copy=False)
    installation_return_type_id = fields.Many2one(
        'stock.picking.type', string='Tipo de operación: Devolución', copy=False)
    installation_consume_type_id = fields.Many2one(
        'stock.picking.type', string='Tipo de operación: Consumo', copy=False)
    installation_release_type_id = fields.Many2one(
        'stock.picking.type', string='Tipo de operación: Liberación', copy=False)

    def _setup_installation_material_control(self):
        """Crea (si faltan) las ubicaciones y tipos de operación de instalación. Idempotente."""
        Location = self.env['stock.location'].sudo()
        PickingType = self.env['stock.picking.type'].sudo()
        customer_loc = self.env.ref('stock.stock_location_customers', raise_if_not_found=False)

        for wh in self:
            wh_s = wh.sudo()
            vals = {}

            if not wh_s.installation_reserved_loc_id:
                reserved = Location.create({
                    'name': _('Reservado Instalaciones'),
                    'usage': 'internal',
                    'location_id': wh_s.view_location_id.id,
                    'company_id': wh_s.company_id.id,
                })
                vals['installation_reserved_loc_id'] = reserved.id
            reserved = wh_s.installation_reserved_loc_id or Location.browse(
                vals.get('installation_reserved_loc_id'))

            if not wh_s.installation_installer_loc_id:
                installer = Location.create({
                    'name': _('En Poder del Instalador'),
                    'usage': 'internal',
                    'location_id': wh_s.view_location_id.id,
                    'company_id': wh_s.company_id.id,
                })
                vals['installation_installer_loc_id'] = installer.id
            installer = wh_s.installation_installer_loc_id or Location.browse(
                vals.get('installation_installer_loc_id'))

            stock_loc = wh_s.lot_stock_id

            def _ensure_type(field, name, code_suffix, src, dest):
                if getattr(wh_s, field):
                    return
                ptype = PickingType.create({
                    'name': name,
                    'code': 'internal',
                    'sequence_code': '%s-%s' % (wh_s.code or 'WH', code_suffix),
                    'warehouse_id': wh_s.id,
                    'company_id': wh_s.company_id.id,
                    'default_location_src_id': src.id if src else False,
                    'default_location_dest_id': dest.id if dest else False,
                })
                vals[field] = ptype.id

            _ensure_type('installation_reserve_type_id',
                         _('Reserva Instalaciones'), 'INSTRES', stock_loc, reserved)
            _ensure_type('installation_withdraw_type_id',
                         _('Retiro para Instalación'), 'INSTRET', reserved, installer)
            _ensure_type('installation_return_type_id',
                         _('Devolución de Instalación'), 'INSTDEV', installer, reserved)
            _ensure_type('installation_consume_type_id',
                         _('Consumo de Instalación'), 'INSTCON', installer, customer_loc)
            _ensure_type('installation_release_type_id',
                         _('Liberación de Sobrante'), 'INSTLIB', reserved, stock_loc)

            if vals:
                wh_s.write(vals)
        return True
