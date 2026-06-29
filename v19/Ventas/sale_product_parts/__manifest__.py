# -*- coding: utf-8 -*-
{
    'name': 'Despiece de Productos para Ventas',
    'version': '19.0.1.0.0',
    'summary': 'Asocia piezas y repuestos a productos e insértalos en pedidos de venta',
    'description': """
        Permite asociar un listado de piezas, repuestos o partes a cualquier producto.
        Desde una cotización o pedido de venta, el vendedor puede visualizar e insertar
        las piezas asociadas como líneas reales de venta con su precio de venta normal.

        Características v2:
        - Buscador nativo de Odoo con filtros y grupos en el selector de piezas.
        - Selección múltiple nativa (checkboxes de fila).
        - Botón "Insertar en pedido" en la cabecera del selector.
        - Botón de actualización de cantidades en la línea del pedido.
        - Stock disponible visible en el selector de piezas.
        - Sin links en la lista de piezas.
    """,
    'category': 'Sales/Sales',
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': [
        'sale_management',
        'uom',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/product_template_views.xml',
        'views/product_part_info_wizard_views.xml',
        'views/product_part_selection_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
