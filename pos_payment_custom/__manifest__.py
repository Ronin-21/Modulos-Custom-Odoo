{
    'name': 'POS Metodos de Pago con Descuentos y Recargos',
    'version': '18.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'author': 'Abel Alejandro Acuña',
    'license': 'LGPL-3',
    'depends': ['point_of_sale'],
    'data': [
        'views/pos_payment_method_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'pos_payment_custom/static/src/css/pos_payment_adjustment.css',
        ],
        'point_of_sale.assets_prod': [
            'pos_payment_custom/static/src/js/pos_payment_adjustment.js',
            'pos_payment_custom/static/src/xml/pos_payment_adjustment.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
}