{
    'name': 'Actualización Automática de Costo de Producto',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Purchase',
    'summary': (
        'Actualiza y sincroniza standard_price: Standard (último o promedio simple) '
        'y AVCO (replicación del promedio real). Soporta facturas directas sin OC.'
    ),
    'description': """
Auto Update Cost v1 (Odoo 19)
==============================

Migración a Odoo 19 del módulo auto_update_cost v2 (Odoo 18).

Cambios respecto a la versión 18:
- product.type: solo 'consu' y 'service' (storable y consumable unificados en 'consu').
- Context key disable_auto_svl → disable_auto_revaluation (cambio en product.product.write de Odoo 19).
""",
    'author': 'Abel Alejandro Acuña',
    'website': 'https://ronin-webdesign.vercel.app/',
    'license': 'LGPL-3',
    'depends': ['purchase', 'stock', 'account'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
