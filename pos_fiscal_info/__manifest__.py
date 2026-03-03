# -*- coding: utf-8 -*-
{
    "name": "POS Fiscal Info",
    "version": "18.0.1.0.0",
    "author": "Custom Development",
    "website": "https://www.example.com",
    "license": "LGPL-3",
    "category": "Point of Sale",
    "summary": "Muestra información fiscal (factura/estado) en órdenes del POS",
    "description": """
        POS Fiscal Info
        ===============
        Extiende las órdenes del Point of Sale para mostrar:
        - Número de factura vinculada (account.move)
        - Estado fiscal visual (facturada / sin factura)
        - Filtros y búsqueda en backend
        - Columna adicional en el TicketScreen del POS frontend
    """,
    "depends": [
        "point_of_sale",
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/pos_config_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_fiscal_info/static/src/js/ticket_screen_fiscal_column.js",
            "pos_fiscal_info/static/src/js/ticket_screen_payment_methods_column.js",
            "pos_fiscal_info/static/src/js/ticket_screen_column_toggle.js",
            "pos_fiscal_info/static/src/scss/fiscal_info_ui.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}