{
    'name': 'POS Métodos de Pago con Descuentos y Recargos',
    'version': '18.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'author': 'Abel Alejandro Acuña',
    'license': 'LGPL-3',
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_payment_method_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_payment_custom/static/src/js/pos_payment_adjustment.js',
            'pos_payment_custom/static/src/xml/cash_discount_card.xml',
            'pos_payment_custom/static/src/scss/cash_discount_ui.scss',
        ],
    },
    'installable': True,
    'auto_install': False,
}