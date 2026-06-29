# -*- coding: utf-8 -*-
{
    'name': 'PRS Tarjetas y Cash Flow',
    'version': '19.0.1.0.0',
    'summary': 'Tarjetas, planes de cuotas y configuracion de comisiones/acreditacion para Payment Register',
    'description': """
Modulo glue extraido de payment_register_statement_v19.

Incluye el modelo base account.card / account.card.installment (inspirado en
card_installment de ADHOC SA) y lo extiende con campos propios de Payment Register:
acreditacion por dias, comisiones, IVA, retenciones y vinculacion con payment.method.

Tambien contiene los modelos prs.payment.method.internal.config y
prs.payment.method.brand.plan para configurar marcas y planes directamente
sobre los metodos de pago nativos de Odoo.
    """,
    'author': '',
    'website': '',
    'license': 'LGPL-3',
    'category': 'Accounting/Payments',

    'depends': [
        'payment_register_statement_v19',
    ],

    'data': [
        'security/ir.model.access.csv',
        'security/account_card_rules.xml',
        'data/decimal_installment_coefficient.xml',
        'data/account_card.xml',
        'views/payment_method_internal_views.xml',
        'views/prs_card_provider_views.xml',
        'views/account_card_prs_views.xml',
        'views/account_journal_card_views.xml',
        'views/prs_accreditation_confirm_wizard_views.xml',
        'views/prs_card_assign_wizard_views.xml',
        'views/account_payment_register_card_views.xml',
        'views/account_payment_card_views.xml',
        'views/res_config_settings_card_views.xml',
        'views/prs_money_flow_card_views.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'payment_register_statement_card_v19/static/src/bank_rec_button/accreditation_button_service.js',
        ],
    },

    'installable': True,
    'application': False,
    'auto_install': False,
}
