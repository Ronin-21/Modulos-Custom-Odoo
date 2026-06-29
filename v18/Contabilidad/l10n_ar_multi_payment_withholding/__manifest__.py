# -*- coding: utf-8 -*-
{
    "name": "Argentina Multi-Payment & Withholding Usability",
    "summary": "Retenciones editables, multi-pago y TC de factura para la localización argentina",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations",
    "license": "LGPL-3",
    "author": "Alderete Informática",
    "depends": [
        "l10n_ar_withholding",
        "l10n_latam_check",
    ],
    "data": [
        "security/ir.model.access.csv",
        "report/multi_payment_summary_report.xml",
        "views/account_payment_register_views.xml",
        "views/account_payment_views.xml",
        "views/account_move_views.xml",
        "views/l10n_ar_withholding_edit_views.xml",
    ],
    "installable": True,
    "application": False,
}