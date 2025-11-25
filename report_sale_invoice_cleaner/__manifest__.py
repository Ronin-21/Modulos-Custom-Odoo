# -*- coding: utf-8 -*-
{
    "name": "Reportes limpios de ventas y facturas (AR)",
    "version": "18.0.1.0.0",
    "summary": "Encabezado comercial en cotizaciones y facturas; oculta datos fiscales por diario",
    "description": """
QWeb para sale.order e invoices: header comercial (sin datos fiscales) y control por diario.
Compat AR (l10n_ar / l10n_latam_invoice_document).
""",
    "category": "Sales",
    "author": "Abel Alejandro Acuña",
    "depends": [
        "sale",
        "account",
        "l10n_ar",
        "l10n_latam_invoice_document",
    ],
    "data": [
        "views/account_journal_view.xml",
        "views/report_saleorder_clean.xml",
        "views/report_invoice_clean.xml",
        # MRP Reports Clean
        "views/report_internal_layout_clean.xml",
        "views/report_mrporder_clean.xml",
        "views/report_mrp_production_components_clean.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}