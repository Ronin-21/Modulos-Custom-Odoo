{
    'name': 'Control de Stock Negativo',
    'version': '18.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Módulo para controlar y prevenir operaciones con stock negativo',
    'description': """
Valida stock disponible antes de confirmar operaciones:
- Órdenes de Venta: No permite confirmar sin stock
- Órdenes de Entrega: No permite validar sin stock
- Órdenes de Fabricación: No permite confirmar sin insumos
- Traslados Internos: No permite validar sin stock en origen
- Ajustes de Inventario: No permite validar con stock negativo

Muestra información clara de:
- Stock disponible
- Stock pronosticado
- Cantidad solicitada/requerida
""",
    'author': 'Abel Acuña',
    'license': 'LGPL-3',
    'depends': ['sale_management', 'stock', 'mrp'],
    'data': [],
    'installable': True,
    'application': False,
}