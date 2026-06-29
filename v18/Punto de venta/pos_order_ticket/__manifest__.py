# -*- coding: utf-8 -*-
{
    "name": "POS Order Ticket (Heladería)",
    'version': '18.0.1.0.0',
    "category": "Point of Sale",
    "summary": "Imprime ticket de pedido (comanda) en POS normal",
    "author": "Abel Alejandro Acuña",
    "website": "https://ronin-webdesign.vercel.app/",
    "depends": ["point_of_sale"],
    "data": [
        "views/pos_config_view.xml",
    ],
    "assets": {
        # En Odoo 18, el POS carga aquí normalmente
        "point_of_sale._assets_pos": [
            "pos_order_ticket/static/src/js/order_ticket_button.js",
            "pos_order_ticket/static/src/xml/order_ticket_templates.xml",
        ],
        # (Opcional) si querés cubrir otros escenarios:
        # "point_of_sale.assets": [
        #     "pos_order_ticket/static/src/js/order_ticket_button.js",
        #     "pos_order_ticket/static/src/xml/order_ticket_templates.xml",
        # ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
