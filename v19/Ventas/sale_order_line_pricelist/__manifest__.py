{
    'name': 'Lista de Precios por Línea de Venta',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Permite definir una lista de precios individual por línea en órdenes de venta',
    'author': 'Alderete Informática',
    'license': 'LGPL-3',
    'depends': ['sale', 'account'],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
