{
    'name': 'Actualización Automática de Costo de Producto',
    'version': '18.0.2.0.0',
    'category': 'Inventory/Purchase',
    'summary': (
        'Actualiza y sincroniza standard_price: Standard (último o promedio simple) '
        'y AVCO (replicación del promedio real). Soporta facturas directas sin OC.'
    ),
    'description': """
Auto Update Cost v2
===================

Versión 2 — cambios principales respecto a v1:

CORRECCIONES
- Fuente única de config: toda la lógica lee desde res.company._auc_config().
  La UI de Ajustes ahora afecta efectivamente el comportamiento del módulo.
- button_confirm llama a super() primero; si la confirmación falla, los costos no se tocan.
- Costo en chatter siempre corresponde a la compañía de la transacción (no a la última iteración).
- AVCO en chatter muestra el costo convertido, no el costo base sin conversión.
- _calculate_bom_cost aplica product_efficiency para reflejar merma/scrap real.
- message_post en BoM se hace con contexto de compañía correcto (multi-empresa).
- Config se lee una sola vez por transacción (mejora de performance).
- Recalculo BoM deduplicado: un solo write por (producto final, compañía).
- Manejo de errores por compañía: un fallo en una compañía no aborta las demás.

NUEVA FUNCIONALIDAD
- Facturas directas sin OC: al validar una factura de proveedor creada manualmente
  (sin orden de compra), el módulo actualiza costos Standard y replica AVCO igual
  que si viniera de una OC.
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
