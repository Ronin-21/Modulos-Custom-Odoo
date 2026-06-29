{
    'name': 'Ubicaciones de Producto por Sucursal',
    'version': '19.0.1.0.0',
    'summary': (
        'Define ubicaciones habituales por producto y almacén/sucursal. '
        'Aplica automáticamente en recepciones de compra y transferencias internas.'
    ),
    'description': """
Ubicaciones de Producto por Sucursal
=====================================

Permite definir, para cada producto y almacén/sucursal, una **ubicación interna habitual**.

La configuración se aplica automáticamente en:
- Recepciones de órdenes de compra
- Transferencias internas entre sucursales/almacenes

Características:
- Maestro de configuración por Producto + Empresa + Almacén
- Validaciones de jerarquía de ubicación y multiempresa
- Parámetros configurables (advertir vs. bloquear si falta configuración)
- Sin modificar rutas globales ni reglas de abastecimiento
- Botón manual de re-aplicación en albaranes
    """,
    'category': 'Inventory/Configuration',
    'author': '',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'purchase',
        'purchase_stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_product_branch_location_views.xml',
        'views/res_config_settings_views.xml',
        'views/stock_picking_views.xml',
        'views/stock_inventory_init_wizard_views.xml',
        'views/stock_inventory_import_wizard_views.xml',
        'views/stock_interbranch_transfer_wizard_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
