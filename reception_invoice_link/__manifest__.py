{
    'name': 'Vincular Recepción a Factura',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Accounting',
    'summary': 'Vinculación entre órdenes de recepción y facturas de proveedor',
    'description': """
        Módulo para vincular órdenes de recepción de productos (stock.picking)
        con facturas de proveedores (account.move).
        
        Características:
        - Vincular recepciones a facturas desde Contabilidad
        - Visualizar recepciones vinculadas en la factura
        - Validar que proveedor coincida entre recepción y factura
        - Cálculo automático del monto total recepcionado
        - Búsqueda de recepciones disponibles por proveedor
        - Flujo de trabajo seguro con validaciones
    """,
    'author': 'Tu Empresa',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_picking_views.xml',
        'views/account_move_views.xml',
        'views/reception_invoice_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    #'images': ['static/description/icon.png'],
}