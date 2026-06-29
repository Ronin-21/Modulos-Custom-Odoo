{
    "name": "Descuento por Litros en Ventas",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "summary": "Descuentos automáticos por volumen en órdenes de venta",
    "description": """
    Módulo para gestión de descuentos por volumen basados en litros o unidades vendidas.

    Funcionalidades principales:
    - Cálculo automático del total de litros/unidades en pedidos de venta según la UdM del producto.
    - Aplicación de descuentos por volumen mediante reglas configurables.
    - Descuento automático aplicado como porcentaje sobre las líneas de la orden.
    - Respeta descuentos manuales ingresados por el usuario (no los sobrescribe).
    - Activación/desactivación global del sistema desde Ajustes.
    - Visualización clara del total de litros y del descuento aplicado en la orden.
    - Integración nativa con el flujo estándar de ventas y facturación de Odoo.

    Diseñado para empresas que trabajan con productos por volumen y requieren reglas de descuento flexibles y controladas.
    """,
    "author": "Abel Alejandro Acuña",
    "website": "https://ronin-webdesign.vercel.app/",
    "depends": [
        "sale",
        "product",
        "sale_management",
        "uom",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/discount_rule_views.xml",
        "views/res_config_settings_views.xml",
        "views/sale_order_view.xml",
        "views/sale_order_tree_view.xml",
        "views/sale_order_report.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}