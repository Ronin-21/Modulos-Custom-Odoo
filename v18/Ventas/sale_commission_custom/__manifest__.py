# -*- coding: utf-8 -*-
{
    'name': 'Comisiones de Vendedores',
    'version': '18.0.1.1.0',
    'summary': 'Gestión de comisiones sobre facturas efectivamente pagadas',
    'description': """
        Módulo de comisiones para vendedores.
        La comisión se crea al confirmar la factura (estado Pendiente de pago)
        y pasa a Ganada cuando la factura queda completamente cobrada.
        Incluye liquidaciones por vendedor y período.

        v1.2.0 - Nuevo flujo de estados:
        - Factura confirmada (posted) → comisión creada en estado DRAFT
          (Pendiente de pago). Visible desde que se emite la factura.
        - Pago conciliado → comisión pasa a EARNED (Ganada).
        - Si se desconcilia el pago, la comisión vuelve a DRAFT.
        - Si la factura vuelve a borrador, la comisión se cancela.
        - Cron actualizado para manejar ambos pasos del flujo.

        v1.1.0 - Correcciones:
        - FIX: Hook en AccountPartialReconcile para generación confiable.
        - FIX: Constraint de unicidad en Python (NULL safe).
        - FIX: Estado 'paid' en sale.order.commission_state.
        - FIX: Preview del wizard sincronizado con commission_start_date.
        - FIX: Cron usa fecha de pago efectivo.
        - FIX: Protección de borrado físico de comisiones.
        - FIX: Implementación de negative_adjustment en notas de crédito.
        - NEW: Vista de porcentaje personalizado en formulario de usuario.
    """,
    'author': 'Desarrollo Custom',
    'category': 'Sales/Sales',
    'depends': [
        'sale',
        'account',
        'sale_management',
        'hr',
    ],
    'data': [
        'security/sale_commission_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'report/sale_commission_reports.xml',
        'report/sale_commission_report_templates.xml',
        'views/res_users_views.xml',
        'views/sale_commission_config_views.xml',
        'views/sale_commission_line_views.xml',
        'views/sale_commission_settlement_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'wizard/sale_commission_settlement_wizard_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
