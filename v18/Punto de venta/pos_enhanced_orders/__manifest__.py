# -*- coding: utf-8 -*-
{
    "name": "POS Enhanced Orders",
    "summary": (
        "Pantalla de tickets mejorada con columnas configurables, "
        "seguimiento de facturas, métodos de pago y backport de "
        "mejoras de facturación del POS de Odoo 19"
    ),
    "version": "18.0.1.0.0",
    "category": "Point of Sale",
    "author": "Abel Alejandro Acuña",
    "website": "https://ronin-webdesign.vercel.app/",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "account",
    ],
    "data": [
        "security/pos_enhanced_orders_security.xml",
        "security/ir.model.access.csv",
        "views/pos_config_views.xml",
        "views/res_config_settings_views.xml",
        "views/pos_draft_invoice_confirmation_views.xml",
        "views/res_users_views.xml",
        "views/pos_payment_method_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            # Estilos
            "pos_enhanced_orders/static/src/scss/fiscal_info_ui.scss",
            "pos_enhanced_orders/static/src/scss/draft_invoice_confirmation.scss",
            # Widgets del wizard
            "pos_enhanced_orders/static/src/widgets/draft_invoice_message_field.js",
            "pos_enhanced_orders/static/src/widgets/draft_invoice_actions_field.js",
            # Columnas y funcionalidad de TicketScreen
            "pos_enhanced_orders/static/src/js/ticket_screen_column_toggle.js",
            "pos_enhanced_orders/static/src/js/ticket_screen_fiscal_column.js",
            "pos_enhanced_orders/static/src/js/ticket_screen_invoice_state_column.js",
            "pos_enhanced_orders/static/src/js/ticket_screen_payment_methods_column.js",
            "pos_enhanced_orders/static/src/js/ticket_screen_invoice_state_filter.js",
            "pos_enhanced_orders/static/src/js/ticket_screen_confirm_invoice.js",
            # Plantillas
            # Overrides v19
            "pos_enhanced_orders/static/src/overrides/payment_screen_patch.js",
            "pos_enhanced_orders/static/src/overrides/invoice_button_patch.js",
            "pos_enhanced_orders/static/src/overrides/closing_popup_patch.js",
            "pos_enhanced_orders/static/src/overrides/pos_store_closing_notification_patch.js",
        ],
        "web.assets_backend": [
            "pos_enhanced_orders/static/src/scss/draft_invoice_confirmation.scss",
            "pos_enhanced_orders/static/src/widgets/draft_invoice_message_field.js",
            "pos_enhanced_orders/static/src/widgets/draft_invoice_actions_field.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
