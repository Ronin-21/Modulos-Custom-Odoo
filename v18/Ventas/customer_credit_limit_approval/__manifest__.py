{
    'name': "Límite de Crédito del Cliente con Aprobación",
    'version': '18.0.1.0',
    'summary': "Control de límite de crédito en ventas con flujo de aprobación",
    'description': """
Activa y configura límite de crédito por cliente en Órdenes de Venta.
Bloquea la confirmación cuando la deuda supera el límite y dispara un flujo
de aprobación por gerencia con notificaciones y actividades.
Para integración con el Punto de Venta instalar: customer_credit_limit_approval_pos
""",
    'author': "Abel Alejandro Acuña",
    'website': "",
    'category': 'Sales',
    'depends': [
        'sale_management',
    ],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'views/res_partner.xml',
        'views/sale_order.xml',
        'views/sale_order_credit_views.xml',
        'views/credit_partner_analysis_views.xml',
        'reports/partner_account_statement.xml',
        'wizard/credit_approval_wizard.xml',
        'wizard/credit_statement_wizard.xml',
        'wizard/credit_warning_wizard.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
