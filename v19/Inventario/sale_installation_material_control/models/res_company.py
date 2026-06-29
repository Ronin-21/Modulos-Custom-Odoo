# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    installation_allow_close_with_installer_material = fields.Boolean(
        string='Permitir cierre con material en poder del instalador',
        default=False,
        help='Si está desactivado, al cerrar una instalación con material todavía en poder del '
             'instalador se exige una confirmación explícita en el asistente de cierre.')
    installation_adjust_so_qty_on_close = fields.Boolean(
        string='Ajustar cantidad de venta al cerrar instalación',
        default=True,
        help='Si está activo, al cerrar se ajusta la cantidad de la línea de venta al consumo '
             'real (cantidad efectivamente utilizada).')
