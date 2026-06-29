# -*- coding: utf-8 -*-
{
    'name': 'POS - Recibo/Factura desactivado por defecto',
    'version': '18.0.1.0',
    'category': 'Point of Sale',
    'depends': ['point_of_sale'],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_invoice_off/static/src/js/invoice_default_off.js',
        ],
    },
    'installable': True,
    'application': False,
    "license": "LGPL-3",
}