{
    "name": "Categorías Multi-Empresa",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Asocia categorías de POS y Producto a empresas específicas",
    "description": """
        Categorías Multi-Empresa
        =========================

        Este módulo permite gestionar categorías por empresa en entornos multi-compañía.

        Características principales:
        -----------------------------
        * Campo 'Empresa' en categorías de Punto de Venta (POS)
        * Campo 'Empresa' en categorías de Producto/Inventario
        * Reglas de seguridad automáticas por empresa
        * Las categorías sin empresa asignada son visibles para todas las empresas
        * Filtrado automático según la empresa activa del usuario

        Casos de uso:
        -------------
        * Empresas con diferentes líneas de productos
        * Separación de categorías por unidad de negocio
        * Gestión independiente de catálogos por empresa

        Compatibilidad:
        ---------------
        * Totalmente compatible con el módulo Point of Sale
        * Compatible con gestión de inventario multi-empresa
        * No afecta categorías existentes sin empresa asignada
    """,
    "author": "Abel Alejadro Acuña",
    "website": "https://ronin-webdesign.vercel.app/",
    "depends": [
        "point_of_sale",
        "product",
        "sale_management",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/category_rules.xml",
        "views/pos_category_views.xml",
        "views/product_category_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}