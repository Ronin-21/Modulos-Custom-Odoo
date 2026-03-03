{
    'name': 'Actualización Automática de Costo de Producto',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Purchase',
    'summary': 'Actualiza y sincroniza el costo del producto: Standard (último o promedio simple) y AVCO (replicación del promedio real).',
    'description': """
Auto Update Cost

Este módulo automatiza el mantenimiento del costo del producto (standard_price) con un enfoque seguro para el usuario,
separando claramente el comportamiento según el método de costo del producto:

STANDARD (Costo Standard)
- Último costo: establece el costo según el último precio de compra (configurable por momento: confirmación, recepción o factura).
- Costo promedio (simple): calcula un promedio aritmético de los precios de compra registrados (sin ponderar por stock ni cantidades).
- Compatible con multi-empresa: puede aplicar el mismo costo en la compañía actual o replicarlo a todas las compañías.

AVCO (Costo Promedio / Average)
- Odoo calcula el costo ponderado real por valorización al recibir (stock valuation).
- El módulo NO recalcula AVCO desde órdenes o facturas: únicamente puede replicar a sucursales el promedio real calculado por Odoo,
  y solo al validar recepciones (según configuración).

OTRAS FUNCIONES
- Propagación opcional de cambios manuales de costo a otras compañías (con guardrails para AVCO).
- Conversión automática de moneda al aplicar costos entre compañías.
- Recalculo opcional de costos por Lista de Materiales (BoM) si MRP está instalado.

Notas importantes:
- Incluir IVA en el costo: el cálculo usa importes con impuestos cuando corresponde (según la lógica del módulo).
- Redondeo: el costo se guarda con un máximo de 2 decimales para evitar valores largos por flotantes.
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
