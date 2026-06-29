# -*- coding: utf-8 -*-

from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    # =========================================================================
    # Columnas de TicketScreen (de pos_enhanced_orders)
    # =========================================================================
    show_ticket_col_client = fields.Boolean(string="Columna: Cliente", default=True)
    show_ticket_col_cashier = fields.Boolean(string="Columna: Cajero", default=True)
    show_ticket_col_total = fields.Boolean(string="Columna: Total", default=True)
    show_ticket_col_state = fields.Boolean(string="Columna: Estado", default=True)
    show_ticket_col_table = fields.Boolean(string="Columna: Mesa", default=True)
    show_ticket_col_date = fields.Boolean(string="Columna: Fecha", default=True)
    show_ticket_col_order = fields.Boolean(string="Columna: Número de orden", default=True)
    show_ticket_col_receipt = fields.Boolean(
        string="Columna: Número de recibo",
        default=True,
    )

    # Modificaciones visuales
    show_ticket_receipt_fiscal_info = fields.Boolean(
        string="[LEGACY] Modificar 'Número de recibo' (Factura / Sin factura)",
        default=True,
        help="Campo legacy mantenido por compatibilidad. La columna fiscal ahora se controla con el check de Columna: Número de recibo.",
    )

    # Columnas extra
    show_ticket_col_payments = fields.Boolean(
        string="Columna: Pagos (métodos de pago)",
        default=True,
        help="Muestra una columna con los métodos de pago usados en la orden (Ej: Efectivo, Tarjeta).",
    )
    show_ticket_col_invoice_state = fields.Boolean(
        string="Columna: Estado factura",
        default=True,
        help="Muestra una columna extra con el estado real de la factura (Borrador/Confirmada/Cancelada).",
    )

    # Botón confirmar factura
    show_ticket_btn_confirm_invoice = fields.Boolean(
        string="Botón: Emitir factura borrador",
        default=True,
        help="Cuando la orden tenga una factura en borrador, reutiliza el botón Recibo/Factura del panel derecho para emitirla desde el POS.",
    )

    # =========================================================================
    # Confirmación de facturas borrador al cierre (de pos_v19_invoice_guard)
    # =========================================================================
    confirm_draft_invoices_on_closing = fields.Boolean(
        string="Confirmación de facturas del POS al cierre",
        default=True,
        help=(
            "Al cerrar una sesión del POS con facturas en borrador o no conciliadas, abrir un asistente "
            "para emitirlas, conciliarlas o revisarlas manualmente antes de completar el cierre."
        ),
    )
    auto_reconcile_pos_invoices_on_closing = fields.Boolean(
        string="Conciliar automáticamente facturas emitidas al cerrar",
        default=True,
        help=(
            "Si está activado, las facturas del POS ya registradas pero no conciliadas intentarán "
            "conciliarse automáticamente durante el cierre. Las facturas en borrador seguirán requiriendo intervención manual."
        ),
    )
