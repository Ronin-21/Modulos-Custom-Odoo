# -*- coding: utf-8 -*-
{
    "name": "POS Pantalla de Ordenes Mejorada",
    "version": "18.0.1.0.0",
    "author": "Abel Alejandro Acuña",
    "website": "https://ronin-webdesign.vercel.app/",
    "license": "LGPL-3",
    "category": "Punto de Venta",
    "summary": "Pantalla de tickets del POS mejorada con seguimiento de facturas, métodos de pago y columnas configurables",

    "description": """
POS Pantalla de Órdenes Mejorada
===============================

Mejora completa de la pantalla de tickets/órdenes del Punto de Venta con funciones avanzadas
para una mejor gestión de órdenes y seguimiento de facturación.

Funciones Principales
---------------------
**Gestión de Facturas:**
* Insignias de estado de factura en tiempo real (Borrador, Publicada, Cancelada)
* Confirmación de factura con un clic desde el POS (sin necesidad de ir a Contabilidad)
* Conciliación automática de pagos al confirmar facturas
* Información fiscal visual en los números de comprobante
* Filtros por estado de factura para búsquedas rápidas

**Seguimiento de Pagos:**
* Columna de métodos de pago que muestra todos los tipos de pago utilizados
* Vista rápida de efectivo, tarjeta, transferencia y otros métodos de pago
* Calculado automáticamente a partir de los pagos del POS

**Columnas Configurables:**
* Activar/desactivar cualquier columna desde la configuración del POS
* Ocultar/mostrar: Fecha, Comprobante, Número de Orden, Cliente, Cajero, Total, Estado, Mesa
* Columnas personalizadas: Estado de Factura, Métodos de Pago
* Visibilidad de columnas guardada por configuración de POS

**Filtrado Inteligente:**
* Filtrar órdenes por estado de factura (Sin Factura, Borrador, Publicada, Cancelada)
* Filtros nativos de Odoo disponibles igualmente
* Filtrado rápido del lado del cliente

**Experiencia de Usuario:**
* Insignias codificadas por color para identificación visual rápida
* Actualización automática al hacer clic en órdenes
* Sin necesidad de recargar la página
* Diseño adaptable a móviles (responsive)
* Estilado profesional con SCSS

**Aspectos Técnicos Destacados:**
* Cero dependencias externas (puro Odoo)
* Integración con el framework OWL
* Actualizaciones reactivas de la interfaz
* Manipulación del DOM optimizada
* Caché inteligente para mejor rendimiento

Configuración
-------------
Ir a: Punto de Venta > Configuración > [Tu POS] > Tickets (Columnas y Botones)

Activar/desactivar:
- Columna de estado de factura
- Columna de métodos de pago
- Botón de confirmación de factura
- Cualquier columna estándar de Odoo

Casos de Uso
------------
* Restaurante/Café: Controlar qué órdenes tienen facturas para reportes impositivos
* Retail: Confirmar rápidamente facturas en borrador durante momentos tranquilos
* Multi-pago: Ver al instante qué órdenes usaron métodos de pago mixtos
* Contabilidad: Filtrar y exportar órdenes por estado de factura

Requisitos
----------
* Odoo 18.0 Community o Enterprise
* Módulo Punto de Venta
* Módulo Contabilidad (para funciones de facturas)

Soporte
-------
Para soporte, personalizaciones o solicitudes de funcionalidades:
contact@aldereteis.com
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
            # Funcionalidad principal
            "pos_enhanced_orders/static/src/js/ticket_screen_column_toggle.js",

            # Implementaciones de columnas
            "pos_enhanced_orders/static/src/js/ticket_screen_fiscal_column.js",
            "pos_enhanced_orders/static/src/js/ticket_screen_invoice_state_column.js",
            "pos_enhanced_orders/static/src/js/ticket_screen_payment_methods_column.js",

            # Funciones avanzadas
            "pos_enhanced_orders/static/src/js/ticket_screen_invoice_state_filter.js",
            "pos_enhanced_orders/static/src/js/ticket_screen_confirm_invoice.js",

            # Plantillas
            "pos_enhanced_orders/static/src/xml/ticket_screen_confirm_invoice.xml",

            # Estilos
            "pos_enhanced_orders/static/src/scss/fiscal_info_ui.scss",
        ],
        "point_of_sale.assets": [
            "pos_enhanced_orders/static/src/scss/fiscal_info_ui.scss",
        ],
    },

    """ "images": [
        "static/description/banner.png",
        "static/description/screenshot_invoice_column.png",
        "static/description/screenshot_payment_column.png",
        "static/description/screenshot_filters.png",
        "static/description/screenshot_confirm_button.png",
    ], """

    "installable": True,
    "application": False,
    "auto_install": False,

    # Metadatos de Odoo Apps Store
    "price": 0.00,
    "currency": "USD",
}