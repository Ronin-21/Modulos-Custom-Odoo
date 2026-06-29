{
    'name': 'POS Colores y Logos Personalizados',
    'version': '18.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'author': 'Abel Alejandro Acuña',
    'license': 'LGPL-3',
    'depends': ['point_of_sale'],
    'data': [
        'views/pos_config_branding_views.xml',
    ],
    'assets': {
        'point_of_sale.assets': [
            'pos_custom_colors/static/src/xml/pos_custom_templates.xml',
            'pos_custom_colors/static/src/js/pos_branding_loader.js',
            'pos_custom_colors/static/src/css/pos_custom_styles.css',
        ],
        'point_of_sale._assets_pos': [
            'pos_custom_colors/static/src/xml/pos_custom_templates.xml',
            'pos_custom_colors/static/src/js/pos_branding_loader.js',
            'pos_custom_colors/static/src/css/pos_custom_styles.css',
        ],
    },
    'installable': True,
    'auto_install': False,
}