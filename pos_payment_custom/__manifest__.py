{
    'name': 'POS Métodos de Pago con Descuentos y Recargos',
    'version': '18.0.1.0',
    'category': 'Sales/Point of Sale',
    'author': 'Abel Alejandro Acuña',
    'license': 'LGPL-3',
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_payment_method_views.xml',
        'views/pos_order_views.xml',
        'views/pos_payment_report_views.xml',
        'views/pos_order_coupon_action.xml',
        'views/report_pos_order_views.xml',
        'views/pos_session_report.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_payment_custom/static/src/js/pos_payment_adjustment.js',
            'pos_payment_custom/static/src/js/pos_payment_coupon.js',
            'pos_payment_custom/static/src/js/ticket_screen_coupon_column.js',
            'pos_payment_custom/static/src/js/closing_popup_card_detail.js',

            'pos_payment_custom/static/src/xml/cash_discount_card.xml',
            'pos_payment_custom/static/src/xml/closing_popup_card_detail.xml',
            'pos_payment_custom/static/src/xml/closing_popup_print_buttons.xml',

            'pos_payment_custom/static/src/scss/cash_discount_ui.scss',
        ],
    },
    'installable': True,
    'auto_install': False,
}
