# -*- coding: utf-8 -*-
{
    'name': 'Productos Multi-Empresa',
    'version': '18.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Permite asignar productos a múltiples empresas específicas',
    'depends': ['product', "mrp"],
    'data': [
        'views/product_template_views.xml',
        "views/mrp_bom_views.xml",
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}