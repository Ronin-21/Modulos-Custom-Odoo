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
""",
    'author': "Abel Alejandro Acuña",
    'website': "",
    'category': 'Sales',
    'depends': [
        'sale_management',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner.xml',
        'views/sale_order.xml',
        'wizard/credit_approval_wizard.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
