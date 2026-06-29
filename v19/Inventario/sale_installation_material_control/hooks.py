# -*- coding: utf-8 -*-
"""Post-init: crea ubicaciones y tipos de operación de instalación en cada almacén.

La lógica real vive en ``stock.warehouse._setup_installation_material_control`` para
poder reutilizarse (es idempotente) tanto desde aquí como al crear almacenes nuevos o
al confirmar una venta de instalación.
"""
from odoo import api, SUPERUSER_ID


def post_init_hook(*args, **kwargs):
    env = None
    if len(args) == 1 and hasattr(args[0], 'cr'):
        env = args[0]
    if env is None and len(args) >= 1:
        try:
            env = api.Environment(args[0], SUPERUSER_ID, {})
        except Exception:
            env = None
    if env is None:
        return

    warehouses = env['stock.warehouse'].sudo().search([])
    for warehouse in warehouses:
        warehouse._setup_installation_material_control()
