# -*- coding: utf-8 -*-
{
    'name': 'POS - Ocultar Subtotal e IVA en Tickets',
    'version': '18.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Oculta las líneas de Subtotal e IVA en el ticket no fiscal y precuenta del POS',
    'description': """
        Módulo que oculta las líneas de Subtotal e IVA 21% (l10n_ar)
        en el ticket no fiscal y la precuenta del Punto de Venta.
    """,
    'author': 'Custom',
    'depends': ['point_of_sale', 'l10n_ar'],
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_hide_tax_subtotal/static/src/xml/order_receipt_override.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
