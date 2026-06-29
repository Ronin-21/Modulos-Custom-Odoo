{
    'name': 'Pago Adelantado en Orden de Venta',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Registra pagos adelantados desde Órdenes de Venta antes de facturar',
    'description': """
        Permite registrar un pago real de cliente desde una Orden de Venta confirmada,
        antes de emitir la factura. El pago se publica automáticamente y se aplica
        a la primera factura generada desde esa orden.

        Características:
        - Botón "Registrar Pago Adelantado" en la Orden de Venta confirmada
        - Pago contable real (account.payment) publicado automáticamente
        - Aplicación automática al publicar la primera factura de la orden
        - Comprobante PDF imprimible (no reemplaza factura fiscal)
        - Leyendas visuales en formulario y PDF de factura
        - Compatible con multiempresa
        - Un pago adelantado por orden (v1)
    """,
    'author': 'Custom',
    'depends': [
        'sale_management',
        'account',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'views/res_config_settings_views.xml',
        'views/sale_order_advance_payment_views.xml',
        'views/sale_advance_payment_wizard_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'report/sale_advance_payment_report.xml',
        'report/sale_advance_payment_templates.xml',
        'report/account_move_report_inherit.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
