# -*- coding: utf-8 -*-
import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    x_ar_withholding_total = fields.Monetary(
        string="Total retenciones",
        currency_field="currency_id",
        compute="_compute_x_ar_withholding_summary",
        store=False,
    )

    x_ar_payment_instrument_amount = fields.Monetary(
        string="Importe real medio de pago",
        currency_field="currency_id",
        compute="_compute_x_ar_withholding_summary",
        store=False,
        help="Importe real del cheque, transferencia o efectivo luego de descontar retenciones.",
    )

    x_ar_document_total_amount = fields.Monetary(
        string="Total cancelado",
        currency_field="currency_id",
        compute="_compute_x_ar_withholding_summary",
        store=False,
        help="Total cancelado por el pago, incluyendo retenciones.",
    )

    # Referencia al asiento de retención asociado (solo referencial)
    x_ar_withholding_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Asiento de retención",
        readonly=True,
        copy=False,
        help="Asiento misceláneo de retención generado junto con este pago. "
             "Solo referencial — revertir este pago no afecta la retención.",
    )

    # Líneas de retención del MISC para mostrar en la pestaña del pago
    x_ar_withholding_line_ids = fields.Many2many(
        comodel_name="account.move.line",
        string="Retenciones del multi-pago",
        compute="_compute_x_ar_withholding_line_ids",
        store=False,
    )

    # Campos para el recibo resumido del multi-pago
    x_ar_multi_payment_group_key = fields.Char(
        string="Grupo de múltiple pago",
        copy=False,
        index=True,
    )

    x_ar_multi_receipt_payload = fields.Text(
        string="Payload recibo resumido",
        copy=False,
    )

    x_ar_has_multi_receipt_summary = fields.Boolean(
        string="Tiene recibo resumido",
        compute="_compute_x_ar_has_multi_receipt_summary",
        store=False,
    )

    @api.depends("x_ar_multi_payment_group_key", "x_ar_multi_receipt_payload")
    def _compute_x_ar_has_multi_receipt_summary(self):
        grouped = {
            key: self.search_count([("x_ar_multi_payment_group_key", "=", key)])
            for key in set(self.filtered("x_ar_multi_payment_group_key").mapped("x_ar_multi_payment_group_key"))
        }
        for payment in self:
            payment.x_ar_has_multi_receipt_summary = bool(
                payment.x_ar_multi_payment_group_key
                and payment.x_ar_multi_receipt_payload
                and grouped.get(payment.x_ar_multi_payment_group_key, 0) > 1
            )

    @api.depends("x_ar_withholding_move_id", "x_ar_withholding_move_id.line_ids")
    def _compute_x_ar_withholding_line_ids(self):
        for payment in self:
            if not payment.x_ar_withholding_move_id:
                payment.x_ar_withholding_line_ids = False
                continue
            payment.x_ar_withholding_line_ids = payment.x_ar_withholding_move_id.line_ids.filtered(
                lambda l: l.tax_line_id and l.tax_line_id.l10n_ar_withholding_payment_type
            )

    @api.depends(
        "amount",
        "currency_id",
        "move_id.line_ids.amount_currency",
        "move_id.line_ids.balance",
        "move_id.line_ids.currency_id",
        "move_id.line_ids.tax_line_id",
        "move_id.line_ids.tax_line_id.l10n_ar_withholding_payment_type",
    )
    def _compute_x_ar_withholding_summary(self):
        for payment in self:
            withholding_lines = payment.l10n_ar_withholding_ids.filtered(
                lambda line: line.tax_line_id and line.tax_line_id.l10n_ar_withholding_payment_type
            )
            withholding_total = 0.0
            for line in withholding_lines:
                if payment.currency_id and line.currency_id == payment.currency_id:
                    withholding_total += abs(line.amount_currency)
                else:
                    withholding_total += abs(line.balance)

            payment.x_ar_withholding_total = withholding_total
            payment.x_ar_payment_instrument_amount = payment.amount
            payment.x_ar_document_total_amount = payment.amount + withholding_total

    def _x_ar_is_check_payment_method(self):
        self.ensure_one()
        method_line = self.payment_method_line_id
        if not method_line:
            return False
        code = (method_line.code or "").lower()
        name = " ".join(x for x in [method_line.display_name, method_line.name] if x).lower()
        return code in {
            "in_third_party_checks", "out_third_party_checks", "return_third_party_checks",
            "new_third_party_checks", "own_checks",
        } or "tercero" in name or "terceros" in name or "propio" in name or "propios" in name

    def _x_ar_get_current_check_total(self):
        self.ensure_one()
        total = 0.0
        if hasattr(self, "l10n_latam_new_check_ids") and self.l10n_latam_new_check_ids:
            total += sum(self.l10n_latam_new_check_ids.mapped("amount"))
        if hasattr(self, "l10n_latam_move_check_ids") and self.l10n_latam_move_check_ids:
            total += sum(self.l10n_latam_move_check_ids.mapped("amount"))
        return total

    def write(self, vals):
        """Protege el importe de pagos por cheque para que no quede en 0."""
        if len(self) > 1:
            result = True
            for payment in self:
                result = super(AccountPayment, payment).write(vals) and result
            return result

        payment = self
        write_vals = dict(vals)

        if payment._x_ar_is_check_payment_method() and "amount" in write_vals:
            current_total = payment._x_ar_get_current_check_total()
            if current_total and payment.currency_id and payment.currency_id.compare_amounts(
                write_vals.get("amount", 0.0), current_total
            ) != 0:
                write_vals["amount"] = current_total

        result = super(AccountPayment, payment).write(write_vals)

        if payment._x_ar_is_check_payment_method() and payment.state == "draft":
            current_total = payment._x_ar_get_current_check_total()
            if current_total and payment.currency_id and payment.currency_id.compare_amounts(
                payment.amount, current_total
            ) != 0:
                super(AccountPayment, payment).write({"amount": current_total})

        return result

    def action_draft(self):
        """Advertencia si el pago tiene una retención referenciada."""
        for payment in self:
            if payment.x_ar_withholding_move_id and payment.x_ar_withholding_move_id.state == "posted":
                raise UserError(_(
                    "Este pago tiene un asiento de retención asociado: %s\n\n"
                    "Si revertís este pago, la retención NO se revierte automáticamente. "
                    "Revisá el asiento %s antes de continuar y revertilo manualmente si corresponde."
                ) % (
                    payment.x_ar_withholding_move_id.name,
                    payment.x_ar_withholding_move_id.name,
                ))
        return super().action_draft()

    def _x_ar_get_multi_receipt_group_payments(self):
        self.ensure_one()
        if not self.x_ar_multi_payment_group_key:
            return self.env["account.payment"]
        return self.search([
            ("x_ar_multi_payment_group_key", "=", self.x_ar_multi_payment_group_key),
        ], order="date asc, id asc")

    def _x_ar_get_multi_receipt_payload_dict(self):
        self.ensure_one()
        payload_text = self.x_ar_multi_receipt_payload
        if not payload_text and self.x_ar_multi_payment_group_key:
            sibling = self.search([
                ("x_ar_multi_payment_group_key", "=", self.x_ar_multi_payment_group_key),
                ("x_ar_multi_receipt_payload", "!=", False),
            ], limit=1)
            payload_text = sibling.x_ar_multi_receipt_payload
        if not payload_text:
            return {}
        try:
            return json.loads(payload_text)
        except Exception:
            return {}

    def _x_ar_build_receipt_data_from_payment(self):
        """Construye los datos del recibo directamente desde el pago,
        sin depender del payload JSON. Funciona para cualquier pago."""
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id

        # Facturas relacionadas
        invoices = []
        for move in self.reconciled_bill_ids | self.reconciled_invoice_ids:
            invoices.append({
                "name": move.name or move.ref or "",
                "date": str(move.invoice_date or move.date or ""),
                "amount_total": abs(move.amount_total),
                "applied_amount": abs(move.amount_total - move.amount_residual),
            })

        # Este pago
        payment_rows = [{
            "payment_name": self.name or "/",
            "journal": self.journal_id.display_name or "",
            "method": self.payment_method_line_id.display_name or "",
            "amount": self.amount,
        }]

        # Cheques
        checks = []
        if hasattr(self, "l10n_latam_move_check_ids"):
            for check in self.l10n_latam_move_check_ids:
                checks.append({
                    "type": _("Tercero existente"),
                    "number": check.name or "",
                    "bank": check.bank_id.name or "" if hasattr(check, "bank_id") else "",
                    "payment_date": str(check.payment_date or "") if hasattr(check, "payment_date") else "",
                    "amount": check.amount,
                })

        # Retenciones
        withholdings = []
        for line in self.l10n_ar_withholding_ids:
            withholdings.append({
                "name": line.tax_line_id.name if line.tax_line_id else _("Retención"),
                "base_amount": line.tax_base_amount,
                "amount": abs(line.amount_currency),
            })

        withholding_total = sum(x["amount"] for x in withholdings)
        payment_total = self.amount
        document_total = payment_total + withholding_total

        return {
            "partner_name": self.partner_id.display_name or "",
            "payment_date": str(self.date or ""),
            "currency_name": currency.name if currency else "",
            "document_total": document_total,
            "payment_total": payment_total,
            "withholding_total": withholding_total,
            "invoice_count": len(invoices),
            "payment_names": self.name or "/",
            "invoices": invoices,
            "payments": payment_rows,
            "checks": checks,
            "withholdings": withholdings,
        }

    def _x_ar_get_multi_receipt_data(self):
        self.ensure_one()
        data = self._x_ar_get_multi_receipt_payload_dict()
        group_payments = self._x_ar_get_multi_receipt_group_payments()
        currency = self.currency_id or self.company_id.currency_id

        # Si no hay payload (pago simple o anterior al módulo),
        # construir los datos directamente desde el pago
        if not data:
            return self._x_ar_build_receipt_data_from_payment()

        # Actualizar los datos del payload con los pagos actuales del grupo
        payment_rows = []
        for payment in group_payments:
            payment_rows.append({
                "payment_name": payment.name or "/",
                "journal": payment.journal_id.display_name or "",
                "method": payment.payment_method_line_id.display_name or "",
                "amount": payment.amount,
            })

        if payment_rows:
            data["payments"] = payment_rows
            data["payment_total"] = sum(x["amount"] for x in payment_rows)
            data["payment_names"] = ", ".join(
                x["payment_name"] for x in payment_rows if x.get("payment_name")
            )

        data.setdefault("invoice_count", len(data.get("invoices", [])))
        data.setdefault("withholding_total", 0.0)
        data.setdefault("payment_total", 0.0)
        data.setdefault("document_total", data.get("payment_total", 0.0) + data.get("withholding_total", 0.0))
        data.setdefault("currency_name", currency.name if currency else "")
        return data

    def action_print_multi_payment_summary_receipt(self):
        """Imprime el recibo resumido. Funciona para cualquier pago."""
        payment = self[:1]
        if not payment:
            raise UserError(_("Seleccioná un pago para imprimir el recibo."))
        return self.env.ref(
            "l10n_ar_multi_payment_withholding.action_report_multi_payment_summary_receipt"
        ).report_action(payment)

    def _l10n_ar_get_withholding_base_accounts(self):
        self.ensure_one()
        companies = self.company_id | self.move_id.line_ids.tax_line_id.company_id | self.move_id.line_ids.tax_ids.company_id
        accounts = self.env['account.account']
        for company in companies:
            accounts |= company._l10n_ar_get_withholding_base_account()
        return accounts

    def _synchronize_to_moves(self, changed_fields):
        if not any(field_name in changed_fields for field_name in self._get_trigger_fields_to_synchronize()):
            return
        for pay in self:
            base_accounts = pay._l10n_ar_get_withholding_base_accounts()
            pay.move_id.line_ids.filtered(lambda line: line.account_id in base_accounts).unlink()
        return super()._synchronize_to_moves(changed_fields)
