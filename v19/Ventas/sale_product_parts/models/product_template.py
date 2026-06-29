# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProductTemplate(models.Model):
    """
    Extensión de product.template para agregar la relación con las piezas/repuestos.

    Se agrega:
    - part_ids: listado de piezas asociadas al producto (pestaña en el formulario).
    - part_count: cantidad de piezas activas, usado como indicador visual.
    """
    _inherit = 'product.template'

    part_ids = fields.One2many(
        comodel_name='product.part',
        inverse_name='product_tmpl_id',
        string='Piezas / Repuestos',
        help=(
            'Listado de piezas, repuestos o componentes asociados a este producto. '
            'Desde un pedido de venta, el vendedor puede visualizar e insertar estas '
            'piezas como líneas reales con su precio de venta normal.'
        ),
    )
    part_count = fields.Integer(
        compute='_compute_part_count',
        string='Cantidad de piezas',
        store=True,
        help='Número de piezas/repuestos activos asociados a este producto.',
    )

    @api.depends('part_ids')
    def _compute_part_count(self):
        """
        Computa la cantidad de piezas activas.
        El campo part_ids ya filtra automáticamente las inactivas por el mecanismo
        de 'active' en Odoo.
        """
        for tmpl in self:
            tmpl.part_count = len(tmpl.part_ids)
