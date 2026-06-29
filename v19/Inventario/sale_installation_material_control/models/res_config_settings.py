# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    installation_allow_close_with_installer_material = fields.Boolean(
        related='company_id.installation_allow_close_with_installer_material', readonly=False)
    installation_adjust_so_qty_on_close = fields.Boolean(
        related='company_id.installation_adjust_so_qty_on_close', readonly=False)

    # Configuración por almacén (almacén principal de la compañía)
    installation_warehouse_id = fields.Many2one(
        'stock.warehouse', string='Almacén de instalación',
        domain="[('company_id', '=', company_id)]",
        help='Almacén cuyas ubicaciones y tipos de operación de instalación se configuran abajo.')
    installation_reserved_loc_id = fields.Many2one(
        'stock.location', string='Ubicación Reservado Instalaciones',
        related='installation_warehouse_id.installation_reserved_loc_id', readonly=False)
    installation_installer_loc_id = fields.Many2one(
        'stock.location', string='Ubicación En Poder del Instalador',
        related='installation_warehouse_id.installation_installer_loc_id', readonly=False)
    installation_reserve_type_id = fields.Many2one(
        'stock.picking.type', string='Tipo de operación Reserva',
        related='installation_warehouse_id.installation_reserve_type_id', readonly=False)
    installation_withdraw_type_id = fields.Many2one(
        'stock.picking.type', string='Tipo de operación Retiro',
        related='installation_warehouse_id.installation_withdraw_type_id', readonly=False)
    installation_return_type_id = fields.Many2one(
        'stock.picking.type', string='Tipo de operación Devolución',
        related='installation_warehouse_id.installation_return_type_id', readonly=False)
    installation_consume_type_id = fields.Many2one(
        'stock.picking.type', string='Tipo de operación Consumo',
        related='installation_warehouse_id.installation_consume_type_id', readonly=False)
    installation_release_type_id = fields.Many2one(
        'stock.picking.type', string='Tipo de operación Liberación',
        related='installation_warehouse_id.installation_release_type_id', readonly=False)
