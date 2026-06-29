{
    'name': 'Control de Entregas y Facturación en Órdenes de Venta',
    'version': '18.0.1.0.0',
    'summary': 'Controla la relación entre órdenes de venta, facturación y entregas de mercadería.',
    'description': """
        Este módulo impide validar entregas de mercadería si la orden de venta relacionada
        no tiene una factura confirmada/publicada. Además, muestra una advertencia al crear
        notas de crédito sobre facturas vinculadas a mercadería ya entregada.
    """,
    'author': 'Alderete Informatica',
    'category': 'Sales/Inventory',
    'license': 'LGPL-3',
    'depends': [
        'sale_management',
        'sale_stock',
        'stock',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/refund_delivery_warning_wizard_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
