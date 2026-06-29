# -*- coding: utf-8 -*-
{
    'name': 'Control de Materiales de Instalación',
    'version': '19.0.1.0.0',
    'summary': 'Retiros y devoluciones parciales de materiales de instalación con cierre por '
               'consumo real y facturación de lo efectivamente utilizado',
    'description': """
Control de Materiales de Instalación
====================================

Capa de control sobre venta / proyecto / inventario para gestionar materiales de
instalación que se retiran y devuelven en forma parcial, calculando el consumo real
(retirado - devuelto) y ajustando la venta a facturar al cerrar la instalación.

Flujo: Reservado Instalaciones -> En Poder del Instalador -> (devolución) ->
Consumo (cliente) + Liberación de sobrante a stock libre.
""",
    'author': 'Alderete Informática',
    'website': 'https://github.com/AldereteIS/linea-blanca',
    'category': 'Inventory/Inventory',
    'license': 'LGPL-3',
    'depends': [
        'sale_management',
        'sale_stock',
        'stock',
        'project',
        'sale_project',
        'account',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'wizard/installation_withdrawal_wizard_views.xml',
        'wizard/installation_return_wizard_views.xml',
        'wizard/installation_close_wizard_views.xml',
        'views/installation_material_views.xml',
        'views/sale_order_views.xml',
        'views/stock_picking_views.xml',
        'views/product_template_views.xml',
        'views/project_views.xml',
        'views/res_users_views.xml',
        'views/res_config_settings_views.xml',
        'report/report_actions.xml',
        'report/installation_withdrawal_report.xml',
        'report/installation_return_report.xml',
        'views/menu_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': False,
    'application': True,
}
