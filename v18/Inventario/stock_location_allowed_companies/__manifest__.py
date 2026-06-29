# -*- coding: utf-8 -*-
{
    'name': 'Stock Location — Empresas Permitidas',
    'version': '18.0.1.2.0',
    'category': 'Inventory/Configuration',
    'summary': 'Control de visibilidad de ubicaciones por empresas permitidas en entornos multiempresa',
    'author': 'Custom',
    'depends': ['stock'],
    'data': [
        'security/security.xml',           # Primero: define el grupo
        'security/ir.model.access.csv',    # Segundo: usa el grupo
        'views/stock_location_views.xml',
        'views/stock_picking_type_views.xml',
        'views/stock_rule_views.xml',
        'views/stock_quant_views.xml',
        'views/wizard_init_views.xml',
        'views/wizard_diagnostic_views.xml',
        'views/wizard_empresa_views.xml',
        'views/wizard_cleanup_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
