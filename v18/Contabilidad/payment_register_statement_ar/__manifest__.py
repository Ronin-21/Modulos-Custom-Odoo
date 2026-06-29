# -*- coding: utf-8 -*-
{
    "name": "Payment Register Statement - Argentina",
    "version": "18.0.1.0.0",
    "summary": "Integracion PRS con cheques argentinos (l10n_latam_check)",
    "author": "Alderete IS",
    "category": "Accounting",
    "depends": ["payment_register_statement", "l10n_latam_check"],
    "data": [
        "security/ir.model.access.csv",
        "views/account_journal_check_views.xml",
        "views/prs_check_mass_transfer_view.xml",
        "views/prs_third_party_check_view.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
