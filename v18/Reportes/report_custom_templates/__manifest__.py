# -*- coding: utf-8 -*-
{
    "name": "Gestor de Plantillas de Reportes Personalizadas",
    "version": "18.0.1.0.0",
    "summary": "Sistema flexible de plantillas personalizables para reportes PDF",
    "description": """
Sistema centralizado para gestionar plantillas de reportes PDF:
- Configuración global de colores, logos y textos
- Múltiples plantillas disponibles por módulo (Clean, Simple, Estándar)
- Activar/desactivar reportes personalizados por empresa
- Selector de plantillas dinámico
- Configurable desde interfaz sin tocar código
    """,
    "category": "Technical",
    "author": "Abel Alejandro Acuña",
    "website": "https://github.com/tu-usuario/odoo-modules",
    "depends": [
        "base",
        "sale",
        "purchase",
        "account",
        "l10n_ar",
        "l10n_latam_invoice_document",
        "mrp",
    ],
    "data": [
    # Seguridad
    "security/ir.model.access.csv",
    
    # Configuración
    "views/report_template_config_view.xml",
    "views/report_template_settings_view.xml",
        
    # Templates específicos
    "views/report_invoice_template.xml",
    "views/account_journal_view.xml",
    "views/report_sale_order_template.xml",
    "views/report_mrp_order_template.xml",
    "views/report_mrp_components_template.xml",
    "views/report_payment_receipt_template.xml",
    
    # Datos iniciales
    "data/report_template_data.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
    "external_dependencies": {
        "python": [],
        "bin": [],
    },
}