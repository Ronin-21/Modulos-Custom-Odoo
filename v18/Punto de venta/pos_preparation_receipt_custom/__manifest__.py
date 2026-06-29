# -*- coding: utf-8 -*-
{
    "name": "POS - Comanda (Impresora de Preparación) Personalizada",
    "version": "18.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Personaliza la comanda/ticket que imprimen las impresoras de preparación (cocina/barra).",
    "depends": ["point_of_sale"],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_preparation_receipt_custom/static/src/app/receipt/order_change_receipt_inherit.xml",
            "pos_preparation_receipt_custom/static/src/app/store/pos_store_patch.js",
            "pos_preparation_receipt_custom/static/src/app/receipt/order_change_receipt.scss",
            "pos_preparation_receipt_custom/static/src/app/screens/product_screen/actionpad/resend_preparation_button.xml",
            "pos_preparation_receipt_custom/static/src/app/screens/product_screen/actionpad/resend_preparation_button.js",
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
