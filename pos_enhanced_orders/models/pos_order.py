# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    invoice_name = fields.Char(
        string="Factura",
        compute="_compute_fiscal_info",
        store=True,
        readonly=True,
        index=True,
    )
    is_fiscal = fields.Boolean(
        string="Tiene factura",
        compute="_compute_fiscal_info",
        store=True,
        readonly=True,
        default=False,
    )

    invoice_state = fields.Selection(
        [
            ("no_invoice", "Sin factura"),
            ("draft", "Borrador"),
            ("posted", "Confirmada"),
            ("cancel", "Cancelada"),
        ],
        string="Estado factura",
        compute="_compute_fiscal_info",
        store=True,
        readonly=True,
        index=True,
        default="no_invoice",
    )

    invoice_state_label = fields.Char(
        string="Estado factura (texto)",
        compute="_compute_fiscal_info",
        store=True,
        readonly=True,
    )

    payment_method_names = fields.Char(
        string="Métodos de pago",
        compute="_compute_payment_method_names",
        store=True,
        readonly=True,
    )

    @api.depends("account_move", "account_move.name", "account_move.l10n_latam_document_number", "account_move.state")
    def _compute_fiscal_info(self):
        for order in self:
            inv = order.account_move
            if inv:
                inv_name = (inv.name or "").strip()
                doc_num = (getattr(inv, "l10n_latam_document_number", False) or "").strip()

                if inv_name and inv_name != "/":
                    order.invoice_name = inv_name
                else:
                    order.invoice_name = doc_num or inv_name or False

                order.is_fiscal = True

                st = (inv.state or "draft").strip()
                if st not in ("draft", "posted", "cancel"):
                    st = "draft"

                order.invoice_state = st
                order.invoice_state_label = {
                    "draft": "Borrador",
                    "posted": "Confirmada",
                    "cancel": "Cancelada",
                }.get(st, st)
            else:
                order.invoice_name = False
                order.is_fiscal = False
                order.invoice_state = "no_invoice"
                order.invoice_state_label = "Sin factura"

    @api.depends("payment_ids.payment_method_id")
    def _compute_payment_method_names(self):
        for order in self:
            names = []
            seen = set()
            for pay in order.payment_ids:
                n = (pay.payment_method_id.name or "").strip()
                if n and n not in seen:
                    names.append(n)
                    seen.add(n)
            order.payment_method_names = ", ".join(names) if names else False

    def _export_for_ui(self):
        res = super()._export_for_ui()
        res.update({
            "invoice_name": self.invoice_name or False,
            "is_fiscal": bool(self.is_fiscal),
            "invoice_state": self.invoice_state or "no_invoice",
            "invoice_state_label": self.invoice_state_label or "Sin factura",
            "payment_method_names": self.payment_method_names or False,
        })
        return res

    # ========================================================================
    # MÉTODO PARA EL POS: Confirmar factura + intentar conciliar con pagos
    # ========================================================================
    def pos_fiscal_post_and_reconcile_from_pos(self):
        """
        Llamado desde el POS para:
        1. Postear la factura (action_post)
        2. Intentar conciliar con los pagos del POS (si ya están contabilizados)
        
        Retorna dict con:
        - reconciled: bool (True si quedó totalmente conciliada)
        - amount_residual: float (saldo pendiente)
        - note: str (mensaje explicativo si aplica)
        """
        self.ensure_one()

        # Validar que la orden tenga factura
        if not self.account_move:
            raise UserError("Esta orden no tiene una factura vinculada.")

        invoice = self.account_move

        # Validar que esté en borrador
        if invoice.state != "draft":
            # Ya está posteada o cancelada
            return {
                "reconciled": invoice.payment_state == "paid",
                "amount_residual": invoice.amount_residual,
                "note": f"La factura ya estaba en estado: {invoice.state}",
            }

        # ====================================================================
        # PASO 1: POSTEAR LA FACTURA
        # ====================================================================
        invoice.action_post()

        # ====================================================================
        # PASO 2: INTENTAR CONCILIAR CON PAGOS DEL POS
        # ====================================================================
        # En Odoo POS, los pagos (pos.payment) se contabilizan típicamente:
        # - Al cerrar la sesión (mayoría de casos)
        # - Inmediatamente si es pago electrónico
        #
        # Si los pagos ya generaron asientos (account.move), intentamos conciliar

        reconciled_any = False

        # Buscar pagos de esta orden que tengan account_move (ya contabilizados)
        for pos_payment in self.payment_ids:
            payment_move = pos_payment.account_move_id
            
            if not payment_move or payment_move.state != "posted":
                # Este pago todavía no se contabilizó (típico: cierre de sesión pendiente)
                continue

            # Buscar líneas de pago que sean de cuentas por cobrar (receivable)
            payment_lines = payment_move.line_ids.filtered(
                lambda l: l.account_id.account_type == "asset_receivable" 
                       and not l.reconciled 
                       and l.partner_id == invoice.partner_id
            )

            # Buscar líneas de la factura que sean receivable y no conciliadas
            invoice_lines = invoice.line_ids.filtered(
                lambda l: l.account_id.account_type == "asset_receivable" 
                       and not l.reconciled
            )

            # Intentar conciliar
            if payment_lines and invoice_lines:
                try:
                    (payment_lines | invoice_lines).reconcile()
                    reconciled_any = True
                except Exception as e:
                    # Si falla la conciliación, no es crítico
                    # (puede ser que los montos no coincidan, etc.)
                    pass

        # ====================================================================
        # PASO 3: RETORNAR RESULTADO
        # ====================================================================
        # Refrescar para obtener el estado actualizado
        invoice.invalidate_recordset(['payment_state', 'amount_residual'])

        result = {
            "reconciled": invoice.payment_state == "paid",
            "amount_residual": float(invoice.amount_residual),
            "note": "",
        }

        # Agregar nota explicativa si quedó saldo y no se concilió nada
        if not reconciled_any and invoice.amount_residual > 0:
            result["note"] = (
                "La factura fue confirmada. Los pagos del POS se contabilizarán "
                "al cerrar la sesión, momento en el que se conciliarán automáticamente."
            )

        return result