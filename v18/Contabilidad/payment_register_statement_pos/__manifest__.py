# -*- coding: utf-8 -*-
{
    'name': 'PRS + POS Cash Transfer',
    'version': '18.0.2.0.0',
    'summary': 'Integración entre payment_register_statement y pos_cash_transfer',
    'description': """
        Módulo glue que extiende el depósito de caja POS (pos_cash_transfer)
        con la posibilidad de requerir validación manual del administrador
        antes de acreditar el importe en la caja destino.

        Incluye:
        - Flag "Requerir validación en depósitos POS" en el diario destino
        - Botón "Depósitos POS pendientes" en el cog menu del tablero bancario
        - Wizard de confirmación directamente desde el tablero
        - Menú Contabilidad → Depósitos POS pendientes
    """,
    'author': 'Alderete Informática',
    'license': 'LGPL-3',
    'category': 'Accounting/Point of Sale',

    'depends': [
        'payment_register_statement',
        'pos_cash_transfer',
    ],

    'data': [
        'security/ir.model.access.csv',
        'views/account_journal_view.xml',
        'views/pos_cash_transfer_wizard_view.xml',
        'views/pos_cash_transfer_views.xml',
        'views/prs_pos_deposit_confirm_wizard_view.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'payment_register_statement_pos/static/src/bank_rec_button/pos_deposit_button_service.js',
        ],
    },

    'installable': True,
    'application': False,
    'auto_install': False,
}
