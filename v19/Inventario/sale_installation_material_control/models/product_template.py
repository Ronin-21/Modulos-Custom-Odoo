# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_installation_service = fields.Boolean(
        string='Es servicio de instalación',
        help='Si se marca, cualquier venta que incluya este producto se considera una '
             'instalación y se crea automáticamente el control de materiales al confirmar.')
