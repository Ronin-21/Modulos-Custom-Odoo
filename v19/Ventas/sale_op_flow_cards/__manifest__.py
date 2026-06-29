# -*- coding: utf-8 -*-
{
    'name': 'Integración Sale Op Flow y PRS Tarjetas',
    'version': '19.0.1.0.0',
    'summary': 'Integración de tarjetas PRS con el flujo operativo de ventas',
    'description': """
Módulo glue que conecta payment_register_statement_card_v19 con sale_op_flow.

Permite seleccionar tarjeta y plan de cuotas directamente en el wizard de cobro
de caja. El recargo se aplica desde surcharge_coefficient del plan de cuotas y
se registra como línea de ajuste en la factura usando un producto global configurable.

Al confirmar el cobro, los campos prs_card_id y prs_installment_id se propagan
al account.payment generado, disparando el flujo de liquidación de tarjeta.
    """,
    'author': '',
    'website': '',
    'license': 'LGPL-3',
    'category': 'Sales',

    'depends': [
        'sale_op_flow',
        'payment_register_statement_card_v19',
    ],

    'data': [
        'views/sale_op_flow_config_card_views.xml',
        'views/sale_order_card_views.xml',
        'views/cashier_payment_wizard_card_views.xml',
    ],

    'installable': True,
    'application': False,
    'auto_install': False,
}
