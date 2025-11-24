{
    'name': "Límite de Crédito del Cliente con Aprobación",
    'version': '18.0.1.0',
    'summary': "Control de límite de crédito en ventas con flujo de aprobación",
    'description': """
Activa y configura límite de crédito por cliente. Si el límite de crédito está configurado,
el sistema advertirá o bloqueará la confirmación de una orden de venta cuando el monto adeudado
más el pedido excedan el límite configurado.

Características:
- Configurar límites de crédito por cliente (montos de advertencia y bloqueo).
- Validación automática de límites de crédito en órdenes de venta.
- Flujo de aprobación por gerencia (ventas / administración).
- Registro en el chatter y actividades para los usuarios involucrados.
- Control de permisos mediante reglas de acceso.
- Visibilidad de saldo de clientes en POS por usuario.
""",
    'author': "Abel Alejandro Acuña",
    'website': "",
    'category': 'Sales',
    'depends': [
        'sale_management',
        'point_of_sale',
    ],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'views/pos_config_views.xml',
        'views/res_partner.xml',
        'views/sale_order.xml',
        'wizard/credit_approval_wizard.xml',
    ],
    'assets': {
    # Bundle del POS "nuevo" (en algunas instancias 18 funciona perfecto)
        'point_of_sale.assets': [
            #'customer_credit_limit_approval/static/src/js/pos_credit_limit.js',
            'customer_credit_limit_approval/static/src/js/pos_balance_visibility.js',
            'customer_credit_limit_approval/static/src/scss/pos_balance_visibility.scss',
        ],
        # Bundle del POS "viejo" que tu instancia sí usa
        'point_of_sale._assets_pos': [
            #'customer_credit_limit_approval/static/src/js/pos_credit_limit.js',
            'customer_credit_limit_approval/static/src/js/pos_balance_visibility.js',
            'customer_credit_limit_approval/static/src/scss/pos_balance_visibility.scss',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}