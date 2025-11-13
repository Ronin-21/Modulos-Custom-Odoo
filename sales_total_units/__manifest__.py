{
    "name": "Descuento por Litros en Ventas",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "summary": "Aplica una regla de descuentos según litros vendidos",
    "description": """
        Este módulo agrega:
        - Campo 'Total Units (Litros)' en pedidos de venta.
        - Descuento automático del 5% o 10% según los litros vendidos.
        - El descuento se aplica como una línea negativa no editable.
        - Compatible con facturación y órdenes de venta.
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
    "security/ir.model.access.csv",
    # "views/discount_rule_views.xml",
    "views/sale_order_view.xml",
    "views/sale_order_tree_view.xml",
    "views/sale_order_report.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}