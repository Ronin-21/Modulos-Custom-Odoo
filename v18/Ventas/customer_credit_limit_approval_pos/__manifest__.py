{
    'name': "Límite de Crédito — Integración con Punto de Venta",
    'version': '18.0.1.0',
    'summary': "Extiende el control de crédito al POS: bloqueo en Cuenta Corriente y visibilidad de saldo",
    'description': """
Módulo complementario que integra customer_credit_limit_approval con el Punto de Venta.

Se instala automáticamente cuando ambos módulos base están presentes.

Agrega:
- Bloqueo de tickets POS pagados con "Cuenta de cliente" si el cliente excede su límite.
- Campo amount_due_pos: deuda de tickets POS en Cuenta Corriente aún no contabilizados.
- Columna de saldo en el selector de clientes del POS (configurable por terminal).
- Grupo de permisos para controlar quién puede activar la visibilidad de saldo.
""",
    'author': "Abel Alejandro Acuña",
    'website': "",
    'category': 'Point of Sale',
    'depends': [
        'customer_credit_limit_approval',
        'point_of_sale',
    ],
    'data': [
        'security/groups.xml',
        'views/pos_config_views.xml',
        'views/res_partner.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'customer_credit_limit_approval_pos/static/src/js/pos_balance_visibility.js',
            'customer_credit_limit_approval_pos/static/src/scss/pos_balance_visibility.scss',
        ],
    },
    'installable': True,
    'auto_install': True,
    'application': False,
    'license': 'LGPL-3',
}
