{
    'name': 'Columna Número de Factura en Ventas',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'Muestra la numeración de facturas vinculadas en el listado de órdenes de venta.',
    'description': """
        Agrega la columna "Facturación" en el listado de Órdenes de Venta / Cotizaciones,
        mostrando la numeración real de las facturas publicadas vinculadas a cada orden.

        También incluye columna opcional "CAE / ARCA" para autorización fiscal (l10n_ar).
    """,
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': [
        'sale_management',
        'account',
    ],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
