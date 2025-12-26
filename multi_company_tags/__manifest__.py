{
    "name": "Categorias Multi-Empresa",
    "version": "18.0.1.0.0",
    "category": "Manufacturing",
    "summary": "Campo de empresas/sucursales en la Lista de Materiales.",
    "description": """
MRP BoM Multi-Empresa (simple)
==============================

- Agrega un campo Many2many de empresas en la Lista de Materiales.
- Las BoM globales (empresa en blanco) solo se ven en las empresas
  que estén en "Empresas / Sucursales relacionadas".
- NO modifica la lógica interna de MRP (_bom_find, reglas estándar).
""",
    "author": "Abel Alejandro Acuña",
    "website": "https://www.aldereteinformatica.com",
    "depends": [
        "mrp",
        "point_of_sale",
        "product",
        "sale_management",],
    "data": [
        "security/ir.model.access.csv",
        "security/category_rules.xml",
        "views/bom_category_views.xml",
        "views/pos_category_views.xml",
        "views/product_category_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
