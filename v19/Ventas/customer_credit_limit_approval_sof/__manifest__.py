# -*- coding: utf-8 -*-
{
    'name': "Límite de Crédito en Flujo Operativo (puente)",
    'version': '19.0.1.0.0',
    'summary': "Integra el control de límite de crédito con el cobro de caja de sale_op_flow",
    'description': """
Módulo puente entre 'customer_credit_limit_approval_v19' y 'sale_op_flow'.

Aplica el control de límite de crédito en el momento correcto del flujo operativo:
el COBRO de caja, cuando se usa una línea de Cuenta Corriente (pago diferido).

Reglas:
- El control de crédito al confirmar (action_confirm) se NEUTRALIZA para pedidos
  SOF: en ese flujo, confirmar = mandar a caja, antes de elegir efectivo vs CC.
- En el cobro con Cuenta Corriente:
  * Cliente sin 'Crédito activo' -> bloqueo duro (no se puede vender en CC).
  * Cliente con crédito activo que excede el límite -> requiere la autorización
    de un supervisor mediante su PIN/NIP de empleado (hr.employee.pin), validado
    contra los usuarios del grupo sale_op_flow.group_sale_supervisor.
""",
    'author': "Alderete Informática",
    'category': 'Sales',
    'depends': [
        'customer_credit_limit_approval_v19',
        'sale_op_flow',
        'hr',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/ccl_cashier_credit_approval_views.xml',
    ],
    'installable': True,
    'auto_install': True,
    'application': False,
    'license': 'LGPL-3',
}
