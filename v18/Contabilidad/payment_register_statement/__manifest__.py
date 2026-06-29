# -*- coding: utf-8 -*-
{
    'name': "Payment Register → Statement Line (Cash Journals)",
    'version': '18.0.1.0.2',
    'summary': "Auto-create bank statement lines when registering cash payments",
    'description': """
    When you register a payment via a cash journal, this module automatically
    creates and closes the corresponding bank statement line.
    """,
    'author': "Mohamed Elkmeshi",
    'website': "https://github.com/melkmeshi/payment_register_statement",
    'license': 'LGPL-3',
    'category': 'Accounting/Payments',

    'depends': ['account', 'web', 'account_reports'],

    'data': [
        'security/ir.model.access.csv',
        'security/prs_groups.xml',
        'data/prs_statement_view_install.xml',
        'views/account_journal_view.xml',
        'views/account_payment_misc_expense_view.xml',
        'views/account_reconcile_model_misc_expense_view.xml',
        'views/expense_concept_views.xml',
        'views/res_partner_expense_concept_view.xml',
        'views/account_move_expense_concept_view.xml',
        'views/account_payment_expense_concept_view.xml',
        'views/account_payment_search_misc_expense_concept.xml',
        'views/internal_transfer_wizard_view.xml',
        'views/prs_report_menus.xml',
        'views/prs_expense_account_report.xml',
        'views/prs_income_account_report.xml',
        'views/prs_cash_balance_account_report.xml',
        'views/account_payment_statement_assign_view.xml',
        'views/account_payment_register_statement_assign_view.xml',
        # prs_check_mass_transfer_view.xml → movido a payment_register_statement_ar
        'views/prs_bank_statement_action.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'payment_register_statement/static/src/expense_report/prs_account_reports_unfold_fallback.js',
            'payment_register_statement/static/src/cog_menu/internal_transfer_cog_menu.js',
            'payment_register_statement/static/src/cog_menu/internal_transfer_cog_menu.xml',
            'payment_register_statement/static/src/bank_rec_button/internal_transfer_button_service.js',
            'payment_register_statement/static/src/live_refresh/prs_live_balance_refresh.js',
        ],
    },

    'installable': True,
    'application': False,
    'auto_install': False,
}
