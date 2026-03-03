# -*- coding: utf-8 -*-
from odoo import models, fields, api


class PosOrderFiscalInfo(models.Model):
    _inherit = "pos.order"

    # (Si ya existen en tu módulo, dejalos igual)
    invoice_name = fields.Char(string="Número de Factura", compute="_compute_fiscal_info", store=True, readonly=True, index=True)
    is_fiscal = fields.Boolean(string="Es Fiscal", compute="_compute_fiscal_info", store=True, readonly=True, default=False)

    # ✅ NUEVO: métodos de pago en texto
    payment_method_names = fields.Char(
        string="Métodos de pago",
        compute="_compute_payment_method_names",
        store=True,
        readonly=True,
        help="Lista de métodos de pago usados en la orden (Ej: Efectivo, Tarjeta).",
    )

    @api.depends("account_move", "account_move.name", "account_move.l10n_latam_document_number", "account_move.state")
    def _compute_fiscal_info(self):
        for order in self:
            if order.account_move:
                inv = order.account_move
                inv_name = (inv.name or "").strip()
                if inv_name and inv_name != "/":
                    order.invoice_name = inv_name
                else:
                    doc_num = getattr(inv, "l10n_latam_document_number", False) or False
                    order.invoice_name = doc_num or inv_name or False
                order.is_fiscal = True
            else:
                order.invoice_name = False
                order.is_fiscal = False

    @api.depends("payment_ids.payment_method_id", "payment_ids.amount")
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
        result = super()._export_for_ui()
        # fiscal
        result["invoice_name"] = self.invoice_name or False
        result["is_fiscal"] = self.is_fiscal
        # pagos
        result["payment_method_names"] = self.payment_method_names or False
        return result
