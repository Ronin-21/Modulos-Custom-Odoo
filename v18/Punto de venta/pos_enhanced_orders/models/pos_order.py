# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    # =========================================================================
    # Campos stored computed (de pos_enhanced_orders)
    # =========================================================================
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

    # =========================================================================
    # Confirmar factura desde TicketScreen
    # =========================================================================
    def pos_fiscal_post_from_pos(self):
        """Postea una factura borrador desde el POS sin intentar conciliarla.

        Se usa para el botón de TicketScreen "Confirmar factura borrador".
        La conciliación queda para un paso posterior y explícito.
        """
        self.ensure_one()

        if not self.account_move:
            raise UserError(_("Esta orden no tiene una factura vinculada."))

        invoice = self.account_move

        if invoice.state != "draft":
            return {
                "posted": invoice.state == "posted",
                "amount_residual": float(invoice.amount_residual),
                "note": _("La factura ya estaba en estado: %s", invoice.state),
            }

        invoice.action_post()

        if not self._is_invoice_fully_emitted(invoice):
            return {
                "posted": False,
                "amount_residual": float(invoice.amount_residual),
                "note": self._get_invoice_emission_error_message(invoice),
            }

        if self.state not in ("invoiced", "done"):
            self.write({"state": "invoiced"})

        invoice.invalidate_recordset(["payment_state", "amount_residual"])
        residual = float(invoice.amount_residual)
        note = _(
            "La factura fue confirmada correctamente."
        )
        if residual > 0:
            note += " " + _(
                "Quedó saldo pendiente y deberá conciliarse o pagarse manualmente."
            )

        return {
            "posted": True,
            "amount_residual": residual,
            "note": note,
        }

    def pos_fiscal_post_and_reconcile_from_pos(self):
        """Compatibilidad retroactiva: conserva el nombre viejo.

        A partir de esta versión, este flujo ya no concilia automáticamente desde
        TicketScreen. Solo confirma/postea la factura.
        """
        return self.pos_fiscal_post_from_pos()

    # =========================================================================
    # Helpers de facturación (de pos_v19_invoice_guard)
    # =========================================================================
    def _invoice_uses_documents(self, invoice):
        self.ensure_one()
        if not invoice:
            return False
        if "l10n_latam_use_documents" in invoice._fields:
            return bool(invoice.l10n_latam_use_documents)
        journal = invoice.journal_id
        return bool(
            journal
            and "l10n_latam_use_documents" in journal._fields
            and journal.l10n_latam_use_documents
        )

    def _invoice_requires_afip_authorization(self, invoice):
        self.ensure_one()
        if not invoice or not self._invoice_uses_documents(invoice):
            return False

        company = invoice.company_id
        country_code = (
            getattr(company.account_fiscal_country_id, "code", False)
            or getattr(company.country_id, "code", False)
        )
        if country_code != "AR":
            return False

        if hasattr(invoice, "_is_argentina_electronic_invoice"):
            try:
                return bool(invoice._is_argentina_electronic_invoice())
            except Exception:
                _logger.debug(
                    "No se pudo evaluar _is_argentina_electronic_invoice para %s",
                    invoice.display_name,
                    exc_info=True,
                )

        journal = invoice.journal_id
        return bool(journal and getattr(journal, "l10n_ar_afip_ws", False))

    def _requires_draft_invoice_confirmation(self, invoice=None):
        self.ensure_one()
        invoice = invoice or self.account_move
        return bool(invoice)

    def _get_invoice_authorization_code(self, invoice):
        self.ensure_one()
        if not invoice:
            return False
        if "l10n_ar_afip_auth_code" in invoice._fields:
            return invoice.l10n_ar_afip_auth_code or False
        return False

    def _invoice_has_required_authorization(self, invoice):
        self.ensure_one()
        if not invoice:
            return False
        if not self._invoice_requires_afip_authorization(invoice):
            return True
        if "l10n_ar_afip_auth_code" in invoice._fields:
            return bool(invoice.l10n_ar_afip_auth_code)
        if "l10n_ar_afip_result" in invoice._fields:
            return invoice.l10n_ar_afip_result in ("A", "O", "accepted", "approved", "observed")
        return True

    def _is_invoice_fully_emitted(self, invoice):
        self.ensure_one()
        return bool(invoice and invoice.state == "posted" and self._invoice_has_required_authorization(invoice))

    def _get_invoice_state_label(self, invoice):
        self.ensure_one()
        mapping = {
            "draft": _("Borrador"),
            "posted": _("Registrada"),
            "cancel": _("Cancelada"),
        }
        return mapping.get(invoice.state, invoice.state) if invoice else False

    def _get_invoice_cae_display(self, invoice):
        self.ensure_one()
        if not invoice:
            return False
        if not self._invoice_requires_afip_authorization(invoice):
            return _("No aplica")
        auth_code = self._get_invoice_authorization_code(invoice)
        if auth_code:
            return auth_code
        if invoice.state == "draft":
            return _("Pendiente")
        return _("Sin CAE")

    def _get_invoice_emission_error_message(self, invoice):
        self.ensure_one()
        invoice_label = (
            (invoice.display_name or invoice.name or invoice.id)
            if invoice
            else _("sin referencia")
        )
        if (
            invoice
            and invoice.state == "posted"
            and self._invoice_requires_afip_authorization(invoice)
            and not self._invoice_has_required_authorization(invoice)
        ):
            return _(
                "La orden %(order)s no se validó porque la factura %(invoice)s no obtuvo CAE/autorización de AFIP-ARCA.",
                order=self.name,
                invoice=invoice_label,
            )
        if invoice and invoice.state != "draft":
            return _(
                "La orden %(order)s no se validó porque la factura %(invoice)s quedó en estado %(state)s y no pudo emitirse correctamente.",
                order=self.name,
                invoice=invoice_label,
                state=invoice.state,
            )
        return _(
            "La orden %(order)s no se validó porque la factura %(invoice)s no pudo emitirse y quedó en borrador.",
            order=self.name,
            invoice=invoice_label,
        )

    # =========================================================================
    # Reconciliación de pagos POS (de pos_v19_invoice_guard)
    # =========================================================================
    def _get_linked_pos_payment_moves(self):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        return order.payment_ids.mapped("account_move_id").sudo().with_company(order.company_id).exists()

    def _relink_existing_pos_payment_moves(self):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        missing_payments = order._get_pos_payment_moves_drivers().filtered(
            lambda payment: not payment.account_move_id
        )
        if not missing_payments:
            return self.env["account.move"]

        existing_moves = self.env["account.move"].sudo().with_company(order.company_id).search([
            ("move_type", "=", "entry"),
            ("pos_payment_ids", "in", missing_payments.ids),
        ])
        relinked_moves = self.env["account.move"]
        for payment in missing_payments:
            payment_move = existing_moves.filtered(lambda move: payment in move.pos_payment_ids)[:1]
            if payment_move:
                payment.write({"account_move_id": payment_move.id})
                relinked_moves |= payment_move
        return relinked_moves

    def _get_invoice_receivable_account_for_reconciliation(self, invoice=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        if not invoice:
            return self.env["account.account"]

        partner = invoice.partner_id or order.partner_id
        if not partner:
            return self.env["account.account"]

        accounting_partner = self.env["res.partner"]._find_accounting_partner(partner).with_company(order.company_id)
        return accounting_partner.property_account_receivable_id

    def _get_invoice_partner_receivable_lines(self, invoice=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        if not invoice:
            return self.env["account.move.line"]

        receivable_account = order._get_invoice_receivable_account_for_reconciliation(invoice)
        if receivable_account:
            receivable_lines = invoice.line_ids.filtered(
                lambda line: (
                    line.account_id == receivable_account
                    and line.account_id.reconcile
                    and line.display_type in (False, "payment_term")
                )
            )
            if receivable_lines:
                return receivable_lines

        receivable_lines = invoice.line_ids.filtered(
            lambda line: (
                line.account_id.reconcile
                and line.display_type in (False, "payment_term")
                and getattr(line.account_id, "account_type", False) in ("asset_receivable", "liability_payable")
            )
        )
        if not receivable_lines:
            return receivable_lines

        partner = invoice.partner_id or order.partner_id
        if partner:
            accounting_partner = self.env["res.partner"]._find_accounting_partner(partner).with_company(order.company_id)
            partner_lines = receivable_lines.filtered(
                lambda line: not line.partner_id or line.partner_id == accounting_partner
            )
            if partner_lines:
                return partner_lines
        return receivable_lines

    def _get_pos_invoice_payments(self):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        return order.payment_ids.sudo().with_company(order.company_id).filtered(
            lambda payment: (
                not order.currency_id.is_zero(payment.amount)
                and (
                    payment.payment_method_id.type != "pay_later"
                    or payment.payment_method_id.is_credit_sale
                )
            )
        )

    def _get_credit_sale_pos_payments(self):
        self.ensure_one()
        return self._get_pos_invoice_payments().filtered(lambda payment: payment.payment_method_id.is_credit_sale)

    def _get_immediate_pos_payments(self):
        self.ensure_one()
        return self._get_pos_invoice_payments().filtered(lambda payment: not payment.payment_method_id.is_credit_sale)

    def _get_expected_credit_sale_residual(self, invoice=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        if not invoice:
            return 0.0
        credit_sale_amount = sum(order._get_credit_sale_pos_payments().mapped("amount"))
        return abs(credit_sale_amount)

    def _is_invoice_expected_open_by_credit_sale(self, invoice=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        if not invoice or invoice.state != "posted":
            return False
        expected_residual = order._get_expected_credit_sale_residual(invoice)
        if order.currency_id.is_zero(expected_residual):
            return False
        actual_residual = abs(invoice.amount_residual)
        return order.currency_id.compare_amounts(actual_residual, expected_residual) == 0

    def _requires_manual_invoice_followup(self, invoice=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        if not invoice or invoice.state != "posted":
            return False
        if order._is_invoice_paid_with_pos_entry(invoice):
            return False
        if order._is_invoice_expected_open_by_credit_sale(invoice):
            return False
        return True

    def _get_pos_payment_moves_drivers(self):
        self.ensure_one()
        payments = self._get_pos_invoice_payments()
        return payments.filtered(lambda payment: not (payment.is_change and payment.payment_method_id.type == "cash"))

    def _reconcile_invoice_payments_native(self, invoice=None, payment_moves=None):
        """Backport fiel de la reconciliación nativa del POS de Odoo 19."""
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        payment_moves = (payment_moves or order._get_linked_pos_payment_moves()).sudo().with_company(order.company_id)
        if not invoice or invoice.state != "posted" or not payment_moves:
            return self.env["account.move.line"]

        receivable_account = order._get_invoice_receivable_account_for_reconciliation(invoice)
        if not receivable_account or not receivable_account.reconcile:
            return self.env["account.move.line"]

        payment_receivable_lines = payment_moves.pos_payment_ids._get_receivable_lines_for_invoice_reconciliation(receivable_account)
        invoice_receivable_lines = invoice.line_ids.filtered(
            lambda line: line.account_id == receivable_account and not line.reconciled
        )
        if not invoice_receivable_lines or not payment_receivable_lines:
            return payment_receivable_lines

        (payment_receivable_lines | invoice_receivable_lines).sudo().with_company(order.company_id).with_context(
            no_cash_basis=True
        ).reconcile()
        return payment_receivable_lines

    def _get_pos_payment_receivable_lines(self, payment_moves=None, credit_line_ids=None, invoice=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        payment_moves = payment_moves or order._get_linked_pos_payment_moves()
        credit_line_ids = credit_line_ids or payment_moves._context.get("credit_line_ids") or []
        receivable_accounts = order._get_invoice_partner_receivable_lines(invoice).mapped("account_id")
        partner = (invoice.partner_id if invoice else False) or order.partner_id
        accounting_partner = False
        if partner:
            accounting_partner = self.env["res.partner"]._find_accounting_partner(partner).with_company(order.company_id)

        lines = payment_moves.mapped("line_ids").filtered(
            lambda line: line.account_id.reconcile and not line.display_type
        )
        if credit_line_ids:
            return lines.filtered(lambda line: line.id in credit_line_ids)
        if receivable_accounts:
            partner_lines = lines.filtered(
                lambda line: (
                    line.account_id in receivable_accounts
                    and (
                        not accounting_partner
                        or not line.partner_id
                        or line.partner_id == accounting_partner
                    )
                )
            )
            if partner_lines:
                return partner_lines
            lines = lines.filtered(lambda line: line.account_id in receivable_accounts)
        return lines

    def _refresh_invoice_payment_records(self, invoice=None):
        self.ensure_one()
        company = self.company_id
        invoice_id = invoice.id if invoice else False
        self.env.flush_all()
        self.env.invalidate_all()
        order = self.env["pos.order"].browse(self.id).sudo().with_company(company)
        refreshed_invoice = (
            self.env["account.move"].browse(invoice_id).sudo().with_company(company).exists()
            if invoice_id
            else order.account_move.sudo().with_company(company)
        )
        return order, refreshed_invoice

    def _get_open_invoice_partner_receivable_lines(self, invoice=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        return order._get_invoice_partner_receivable_lines(invoice).filtered(lambda line: not line.reconciled)

    def _is_invoice_settled(self, invoice=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        if not invoice or invoice.state != "posted":
            return False

        receivable_lines = order._get_invoice_partner_receivable_lines(invoice)
        if not receivable_lines:
            return invoice.payment_state in ("paid", "in_payment") or order.currency_id.is_zero(abs(invoice.amount_residual))

        return (
            invoice.payment_state in ("paid", "in_payment")
            or all(receivable_lines.mapped("reconciled"))
            or order.currency_id.is_zero(abs(invoice.amount_residual))
        )

    def _get_outstanding_pos_payment_lines(self, invoice=None, payment_moves=None, credit_line_ids=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        if not invoice or invoice.state != "posted":
            return self.env["account.move.line"]

        invoice_receivables = order._get_open_invoice_partner_receivable_lines(invoice)
        if not invoice_receivables:
            return self.env["account.move.line"]

        payment_receivables = order._get_pos_payment_receivable_lines(
            payment_moves=payment_moves,
            credit_line_ids=credit_line_ids,
            invoice=invoice,
        ).filtered(lambda line: not line.reconciled)
        if not payment_receivables:
            return payment_receivables

        invoice_balance = sum(invoice_receivables.mapped("balance"))
        if invoice_balance > 0:
            return payment_receivables.filtered(lambda line: line.balance < 0)
        if invoice_balance < 0:
            return payment_receivables.filtered(lambda line: line.balance > 0)
        return payment_receivables

    def _is_invoice_paid_with_pos_entry(self, invoice=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        if not invoice or invoice.state != "posted":
            return False

        receivable_lines = order._get_invoice_partner_receivable_lines(invoice)
        payments = order._get_pos_payment_moves_drivers()
        payment_moves = order._get_linked_pos_payment_moves()
        invoice_settled = order._is_invoice_settled(invoice)

        if payments and not all(payments.mapped("account_move_id")):
            return False
        if payments and not payment_moves:
            return False
        if not invoice_settled:
            return False
        if not receivable_lines:
            return invoice_settled
        if not payments or not payment_moves:
            return invoice_settled

        payment_receivable_lines = order._get_pos_payment_receivable_lines(
            payment_moves=payment_moves,
            invoice=invoice,
        )
        if not payment_receivable_lines:
            return invoice_settled

        counterpart_lines = receivable_lines.mapped("matched_debit_ids.credit_move_id") | receivable_lines.mapped(
            "matched_credit_ids.debit_move_id"
        )
        shared_full_reconcile = bool(
            payment_receivable_lines.filtered(
                lambda line: line.full_reconcile_id and line.full_reconcile_id in receivable_lines.mapped("full_reconcile_id")
            )
        )
        return bool(counterpart_lines & payment_receivable_lines) or shared_full_reconcile or invoice_settled

    def _get_invoice_payment_error_message(self, invoice=None):
        self.ensure_one()
        invoice = invoice or self.account_move
        invoice_label = (
            invoice.display_name or invoice.name or str(invoice.id)
            if invoice
            else _("sin referencia")
        )
        if self._is_invoice_expected_open_by_credit_sale(invoice):
            return _(
                "La factura %(invoice)s de la orden %(order)s quedó abierta de forma intencional por cuenta corriente.",
                invoice=invoice_label,
                order=self.name,
            )
        payments = self._get_pos_payment_moves_drivers()
        payment_moves = self._get_linked_pos_payment_moves()
        if not payments:
            return _(
                "La factura %(invoice)s de la orden %(order)s quedó emitida, pero la orden no tiene pagos inmediatos del POS para generar su asiento contable de cobro.",
                invoice=invoice_label,
                order=self.name,
            )
        if payments and not all(payments.mapped("account_move_id")):
            return _(
                "La factura %(invoice)s de la orden %(order)s quedó emitida, pero no se pudo generar automáticamente el asiento de pago del POS.",
                invoice=invoice_label,
                order=self.name,
            )
        if not payment_moves:
            return _(
                "La factura %(invoice)s de la orden %(order)s quedó emitida, pero no tiene el asiento de pago del POS asociado.",
                invoice=invoice_label,
                order=self.name,
            )
        return _(
            "La factura %(invoice)s de la orden %(order)s quedó emitida, pero sigue sin quedar pagada con su asiento de pago del POS.",
            invoice=invoice_label,
            order=self.name,
        )

    def _assign_outstanding_pos_payment_lines(self, invoice=None, payment_moves=None, credit_line_ids=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        if not invoice or invoice.state != "posted":
            return self.env["account.move.line"]

        payment_moves = (payment_moves or order._get_linked_pos_payment_moves()).sudo().with_company(order.company_id)
        if not payment_moves:
            return self.env["account.move.line"]

        draft_payment_moves = payment_moves.filtered(lambda move: move.state == "draft")
        if draft_payment_moves:
            try:
                draft_payment_moves.action_post()
            except Exception:
                draft_payment_moves._post(soft=False)

        outstanding_lines = order._get_outstanding_pos_payment_lines(
            invoice=invoice,
            payment_moves=payment_moves,
            credit_line_ids=credit_line_ids,
        )
        for line in outstanding_lines.sorted(lambda l: (l.date_maturity or l.date or fields.Date.today(), l.id)):
            current_order, current_invoice = order._refresh_invoice_payment_records(invoice)
            if not current_invoice or current_invoice.state != "posted":
                break
            if current_order._is_invoice_paid_with_pos_entry(current_invoice):
                break
            open_invoice_lines = current_order._get_open_invoice_partner_receivable_lines(current_invoice)
            if not open_invoice_lines or line.reconciled:
                continue
            try:
                current_invoice.sudo().with_company(current_order.company_id).js_assign_outstanding_line(line.id)
            except Exception:
                _logger.debug(
                    "No se pudo asignar como pendiente el apunte %s para la factura %s de la orden %s",
                    line.display_name,
                    current_invoice.display_name,
                    current_order.display_name,
                    exc_info=True,
                )
        return outstanding_lines

    def _reconcile_invoice_with_payment_moves(self, invoice=None, payment_moves=None, credit_line_ids=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        if not invoice or invoice.state != "posted":
            return self.env["account.move.line"]

        payment_moves = (payment_moves or order._get_linked_pos_payment_moves()).sudo().with_company(order.company_id)
        if not payment_moves:
            return self.env["account.move.line"]

        order._assign_outstanding_pos_payment_lines(
            invoice=invoice,
            payment_moves=payment_moves,
            credit_line_ids=credit_line_ids,
        )
        order, invoice = order._refresh_invoice_payment_records(invoice)

        try:
            payment_receivables = order._reconcile_invoice_payments_native(
                invoice=invoice,
                payment_moves=payment_moves,
            )
        except Exception:
            _logger.debug(
                "No se pudo reconciliar directamente la factura %s con sus asientos POS para la orden %s",
                invoice.display_name,
                order.display_name,
                exc_info=True,
            )
            payment_receivables = self.env["account.move.line"]
        return payment_receivables

    def _remove_invoice_payment_reconciliations(self, invoice=None, payment_moves=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        payment_moves = (payment_moves or order._get_linked_pos_payment_moves()).sudo().with_company(order.company_id)
        reconciled_lines = (
            order._get_invoice_partner_receivable_lines(invoice)
            | order._get_pos_payment_receivable_lines(payment_moves=payment_moves, invoice=invoice)
        ).filtered(
            lambda line: line.account_id.reconcile
            and (line.reconciled or line.matched_debit_ids or line.matched_credit_ids)
        )
        if reconciled_lines:
            reconciled_lines.remove_move_reconcile()

    def _create_pos_payment_moves_using_invoice_account(self, invoice=None, payments=None, is_reverse=False):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        payments = (payments or order._get_pos_invoice_payments()).sudo().with_company(order.company_id)
        if not invoice or invoice.state != "posted" or not payments:
            return self.env["account.move"]

        receivable_lines = order._get_invoice_partner_receivable_lines(invoice)
        receivable_account = receivable_lines[:1].account_id
        if not receivable_account:
            accounting_partner = self.env["res.partner"]._find_accounting_partner(order.partner_id).with_company(order.company_id)
            receivable_account = accounting_partner.property_account_receivable_id

        result = self.env["account.move"]
        credit_line_ids = []
        change_payment = payments.filtered(lambda p: p.is_change and p.payment_method_id.type == "cash")
        payment_to_change = payments.filtered(lambda p: not p.is_change and p.payment_method_id.type == "cash")[:1]

        for payment in payments - change_payment:
            payment_method = payment.payment_method_id
            if payment_method.type == "pay_later" or order.currency_id.is_zero(payment.amount):
                continue

            accounting_partner = self.env["res.partner"]._find_accounting_partner(payment.partner_id or order.partner_id).with_company(order.company_id)
            pos_session = order.session_id
            journal = pos_session.config_id.journal_id
            if change_payment and payment == payment_to_change:
                pos_payment_ids = payment.ids + change_payment.ids
                payment_amount = payment.amount + sum(change_payment.mapped("amount"))
            else:
                pos_payment_ids = payment.ids
                payment_amount = payment.amount

            payment_move = self.env["account.move"].with_context(default_journal_id=journal.id).create({
                "journal_id": journal.id,
                "date": fields.Date.context_today(order, order.date_order),
                "ref": _(
                    "Pago de la factura de %(order)s (%(invoice)s) con %(payment_method)s",
                    order=order.name,
                    invoice=invoice.display_name or invoice.name,
                    payment_method=payment_method.name,
                ),
                "pos_payment_ids": [(6, 0, pos_payment_ids)],
            })
            result |= payment_move
            self.env["pos.payment"].browse(pos_payment_ids).write({"account_move_id": payment_move.id})

            amounts = pos_session._update_amounts(
                {"amount": 0, "amount_converted": 0},
                {"amount": payment_amount},
                payment.payment_date,
            )
            credit_line_vals = pos_session._credit_amounts(
                {
                    "account_id": receivable_account.id,
                    "partner_id": accounting_partner.id,
                    "move_id": payment_move.id,
                },
                amounts["amount"],
                amounts["amount_converted"],
            )
            is_split_transaction = payment.payment_method_id.split_transactions
            if is_split_transaction and is_reverse:
                reversed_move_receivable_account_id = receivable_account.id
            elif is_reverse:
                reversed_move_receivable_account_id = (
                    payment.payment_method_id.receivable_account_id.id
                    or order.company_id.account_default_pos_receivable_account_id.id
                )
            else:
                reversed_move_receivable_account_id = order.company_id.account_default_pos_receivable_account_id.id
            debit_line_vals = pos_session._debit_amounts(
                {
                    "account_id": reversed_move_receivable_account_id,
                    "move_id": payment_move.id,
                    "partner_id": accounting_partner.id if is_split_transaction and is_reverse else False,
                },
                amounts["amount"],
                amounts["amount_converted"],
            )
            lines = self.env["account.move.line"].create([credit_line_vals, debit_line_vals])
            if amounts["amount_converted"] < 0:
                credit_line_ids += lines.filtered(lambda line: line.debit).ids
            else:
                credit_line_ids += lines.filtered(lambda line: line.credit).ids
            payment_move._post()
        return result.with_context(credit_line_ids=credit_line_ids)

    def _create_missing_pos_payment_moves(self, invoice=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        if not invoice or invoice.state != "posted":
            return self.env["account.move"]
        missing_payments = order._get_pos_invoice_payments().filtered(lambda payment: not payment.account_move_id)
        if not missing_payments:
            return self.env["account.move"]
        return missing_payments.sudo().with_company(order.company_id)._create_payment_moves(
            order.session_id.state == "closed"
        )

    def _get_expected_pos_payment_amounts(self):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        payments = order._get_pos_invoice_payments()
        change_payment = payments.filtered(lambda payment: payment.is_change and payment.payment_method_id.type == "cash")
        payment_to_change = payments.filtered(lambda payment: not payment.is_change and payment.payment_method_id.type == "cash")[:1]
        expected = {}
        for payment in payments - change_payment:
            payment_amount = payment.amount
            linked_payments = payment
            if change_payment and payment == payment_to_change:
                payment_amount += sum(change_payment.mapped("amount"))
                linked_payments |= change_payment
            amounts = order.session_id._update_amounts(
                {"amount": 0, "amount_converted": 0},
                {"amount": payment_amount},
                payment.payment_date,
            )
            expected[payment.id] = {
                "payment_amount": payment_amount,
                "amount_converted": abs(amounts["amount_converted"]),
                "linked_payments": linked_payments,
            }
        return expected

    def _find_orphan_pos_payment_move_for_payment(self, payment, invoice=None, candidate_moves=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        if not payment or not invoice:
            return self.env["account.move"]

        receivable_account = order._get_invoice_receivable_account_for_reconciliation(invoice)
        if not receivable_account:
            return self.env["account.move"]

        expected = order._get_expected_pos_payment_amounts().get(payment.id)
        expected_balance = (expected or {}).get("amount_converted")
        company_currency = order.company_id.currency_id
        journal = order.session_id.config_id.journal_id
        ref_tokens = [order.name, payment.payment_method_id.name, invoice.name or invoice.display_name]

        if candidate_moves is None:
            date_value = fields.Date.context_today(order, payment.payment_date or order.date_order)
            candidate_moves = self.env["account.move"].sudo().with_company(order.company_id).search([
                ("move_type", "=", "entry"),
                ("journal_id", "=", journal.id),
                ("state", "in", ("draft", "posted")),
                ("date", "=", date_value),
                ("ref", "ilike", order.name or ""),
            ])
            if not candidate_moves:
                candidate_moves = self.env["account.move"].sudo().with_company(order.company_id).search([
                    ("move_type", "=", "entry"),
                    ("journal_id", "=", journal.id),
                    ("state", "in", ("draft", "posted")),
                    ("ref", "ilike", order.name or ""),
                ])

        candidate_moves = candidate_moves.filtered(
            lambda move: (
                move not in order._get_linked_pos_payment_moves()
                and not (move.pos_payment_ids and (move.pos_payment_ids - order.payment_ids))
                and all(token and token.lower() in (move.ref or "").lower() for token in ref_tokens if token)
            )
        )
        if expected_balance is not None:
            candidate_moves = candidate_moves.filtered(
                lambda move: bool(move.line_ids.filtered(
                    lambda line: (
                        line.account_id == receivable_account
                        and company_currency.is_zero(abs(abs(line.balance) - expected_balance))
                    )
                ))
            )

        if len(candidate_moves) == 1:
            return candidate_moves[:1]

        empty_link_candidates = candidate_moves.filtered(lambda move: not move.pos_payment_ids)
        if len(empty_link_candidates) == 1:
            return empty_link_candidates[:1]
        return self.env["account.move"]

    def _relink_existing_pos_payment_moves_from_ref(self, invoice=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        if not invoice or invoice.state != "posted":
            return self.env["account.move"]

        missing_drivers = order._get_pos_payment_moves_drivers().filtered(lambda payment: not payment.account_move_id)
        if not missing_drivers:
            return self.env["account.move"]

        candidate_moves = self.env["account.move"].sudo().with_company(order.company_id).search([
            ("move_type", "=", "entry"),
            ("journal_id", "=", order.session_id.config_id.journal_id.id),
            ("state", "in", ("draft", "posted")),
            ("ref", "ilike", order.name or ""),
        ])
        relinked_moves = self.env["account.move"]
        expected = order._get_expected_pos_payment_amounts()
        for payment in missing_drivers:
            move = order._find_orphan_pos_payment_move_for_payment(payment, invoice=invoice, candidate_moves=candidate_moves)
            if not move:
                continue
            linked_payments = (expected.get(payment.id) or {}).get("linked_payments") or payment
            linked_payments.write({"account_move_id": move.id})
            relinked_moves |= move
            candidate_moves -= move
        return relinked_moves

    def _force_native_pos_invoice_payment(self, invoice=None):
        """Fuerza la misma secuencia nativa del POS que usa Odoo al facturar una orden."""
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        payments = order._get_pos_invoice_payments()
        if not invoice or invoice.state != "posted" or not payments:
            return self.env["account.move"]

        order._relink_existing_pos_payment_moves()
        payment_moves = order._get_related_pos_payment_moves_for_cleanup()
        if payment_moves:
            order._remove_invoice_payment_reconciliations(invoice=invoice, payment_moves=payment_moves)
            posted_payment_moves = payment_moves.filtered(lambda move: move.state == "posted")
            if posted_payment_moves:
                posted_payment_moves.button_draft()
            payment_moves.unlink()

        payments.write({"account_move_id": False})
        payment_moves = order._apply_invoice_payments(order.session_id.state == "closed")
        order, invoice = order._refresh_invoice_payment_records(invoice)
        if payment_moves and not order._is_invoice_settled(invoice):
            order._assign_outstanding_pos_payment_lines(
                invoice=invoice,
                payment_moves=payment_moves,
                credit_line_ids=payment_moves._context.get("credit_line_ids") or [],
            )
            order._reconcile_invoice_with_payment_moves(
                invoice=invoice,
                payment_moves=payment_moves,
                credit_line_ids=payment_moves._context.get("credit_line_ids") or [],
            )
        return payment_moves

    def _rebuild_pos_invoice_payment_entries(self, invoice=None):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = (invoice or order.account_move).sudo().with_company(order.company_id)
        payments = order._get_pos_invoice_payments()
        if not invoice or invoice.state != "posted" or not payments:
            return self.env["account.move"]

        order._relink_existing_pos_payment_moves()
        payment_moves = order._get_related_pos_payment_moves_for_cleanup()
        order._remove_invoice_payment_reconciliations(invoice=invoice, payment_moves=payment_moves)

        posted_payment_moves = payment_moves.filtered(lambda move: move.state == "posted")
        if posted_payment_moves:
            posted_payment_moves.button_draft()
        if payment_moves:
            payment_moves.unlink()
        payments.write({"account_move_id": False})

        payment_moves = order._apply_invoice_payments(order.session_id.state == "closed")
        order, invoice = order._refresh_invoice_payment_records(invoice)
        order._assign_outstanding_pos_payment_lines(
            invoice=invoice,
            payment_moves=payment_moves,
            credit_line_ids=payment_moves._context.get("credit_line_ids") or [],
        )
        order, invoice = order._refresh_invoice_payment_records(invoice)
        if order._is_invoice_paid_with_pos_entry(invoice):
            return order._get_linked_pos_payment_moves() or payment_moves

        payment_moves = order._get_related_pos_payment_moves_for_cleanup()
        order._remove_invoice_payment_reconciliations(invoice=invoice, payment_moves=payment_moves)
        posted_payment_moves = payment_moves.filtered(lambda move: move.state == "posted")
        if posted_payment_moves:
            posted_payment_moves.button_draft()
        if payment_moves:
            payment_moves.unlink()
        payments.write({"account_move_id": False})

        payment_moves = order._create_pos_payment_moves_using_invoice_account(
            invoice=invoice,
            payments=payments,
            is_reverse=order.session_id.state == "closed",
        )
        order._assign_outstanding_pos_payment_lines(
            invoice=invoice,
            payment_moves=payment_moves,
            credit_line_ids=payment_moves._context.get("credit_line_ids") or [],
        )
        order._reconcile_invoice_with_payment_moves(
            invoice=invoice,
            payment_moves=payment_moves,
            credit_line_ids=payment_moves._context.get("credit_line_ids") or [],
        )
        return payment_moves

    def _ensure_invoice_payment_consistency(self):
        """Garantiza en el cierre que toda factura POS emitida quede pagada."""
        self.ensure_one()
        order, invoice = self._refresh_invoice_payment_records(self.account_move)
        if not invoice or invoice.state != "posted":
            return self.env["account.move"]

        all_invoice_payments = order._get_pos_invoice_payments()
        driver_payments = order._get_pos_payment_moves_drivers()
        if not driver_payments:
            if order._is_invoice_expected_open_by_credit_sale(invoice):
                return self.env["account.move"]
            if order._is_invoice_settled(invoice):
                return self.env["account.move"]
            raise UserError(order._get_invoice_payment_error_message(invoice))

        def _post_and_reconcile(payment_moves):
            payment_moves = payment_moves.sudo().with_company(order.company_id)
            if not payment_moves:
                return payment_moves
            draft_moves = payment_moves.filtered(lambda move: move.state == "draft")
            if draft_moves:
                try:
                    draft_moves.action_post()
                except Exception:
                    draft_moves._post(soft=False)
            try:
                order._reconcile_invoice_payments_native(invoice=invoice, payment_moves=payment_moves)
            except Exception:
                _logger.debug(
                    "No se pudo reconciliar la factura %s con los asientos POS %s de la orden %s.",
                    invoice.display_name,
                    ", ".join(payment_moves.mapped("display_name")),
                    order.display_name,
                    exc_info=True,
                )
            return payment_moves

        order._relink_existing_pos_payment_moves()
        order._relink_existing_pos_payment_moves_from_ref(invoice)
        order, invoice = order._refresh_invoice_payment_records(invoice)

        payment_moves = order._get_linked_pos_payment_moves()
        if payment_moves:
            _post_and_reconcile(payment_moves)
            order, invoice = order._refresh_invoice_payment_records(invoice)
            if order._is_invoice_settled(invoice) and all(order._get_pos_payment_moves_drivers().mapped("account_move_id")):
                return order._get_linked_pos_payment_moves() or payment_moves

            order._remove_invoice_payment_reconciliations(invoice=invoice, payment_moves=payment_moves)
            _post_and_reconcile(payment_moves)
            order, invoice = order._refresh_invoice_payment_records(invoice)
            if order._is_invoice_settled(invoice) and all(order._get_pos_payment_moves_drivers().mapped("account_move_id")):
                return order._get_linked_pos_payment_moves() or payment_moves

        missing_payment_moves = order._create_missing_pos_payment_moves(invoice)
        order, invoice = order._refresh_invoice_payment_records(invoice)
        payment_moves = order._get_linked_pos_payment_moves() | missing_payment_moves
        if payment_moves:
            _post_and_reconcile(payment_moves)
            order, invoice = order._refresh_invoice_payment_records(invoice)
            if order._is_invoice_settled(invoice) and all(order._get_pos_payment_moves_drivers().mapped("account_move_id")):
                return order._get_linked_pos_payment_moves() or payment_moves

        _logger.warning(
            "POS order %s: se reconstruyen los asientos de pago POS para la factura %s porque sigue sin quedar saldada.",
            order.display_name,
            invoice.display_name,
        )
        rebuilt_moves = order._rebuild_pos_invoice_payment_entries(invoice)
        order, invoice = order._refresh_invoice_payment_records(invoice)
        if order._is_invoice_settled(invoice) and all(order._get_pos_payment_moves_drivers().mapped("account_move_id")):
            return order._get_linked_pos_payment_moves() or rebuilt_moves

        final_missing_moves = order._create_missing_pos_payment_moves(invoice)
        order, invoice = order._refresh_invoice_payment_records(invoice)
        final_payment_moves = order._get_linked_pos_payment_moves() | rebuilt_moves | final_missing_moves
        if final_payment_moves:
            _post_and_reconcile(final_payment_moves)
            order._assign_outstanding_pos_payment_lines(
                invoice=invoice,
                payment_moves=final_payment_moves,
                credit_line_ids=final_payment_moves._context.get("credit_line_ids") or [],
            )
            order, invoice = order._refresh_invoice_payment_records(invoice)
            if order._is_invoice_settled(invoice) and all(order._get_pos_payment_moves_drivers().mapped("account_move_id")):
                return order._get_linked_pos_payment_moves() or final_payment_moves

        raise UserError(order._get_invoice_payment_error_message(invoice))

    def _get_related_pos_payment_moves_for_cleanup(self):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        payments = order.payment_ids.sudo().with_company(order.company_id)
        return (
            payments.mapped("account_move_id")
            .sudo()
            .with_company(order.company_id)
            .filtered(
                lambda move: move
                and move.move_type == "entry"
                and not (move.pos_payment_ids - payments)
            )
        )

    def _cleanup_draft_invoice_artifacts(self):
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        invoice = order.account_move.sudo().with_company(order.company_id)
        payments = order.payment_ids.sudo().with_company(order.company_id)
        payment_moves = order._get_related_pos_payment_moves_for_cleanup()

        invoice_label = (
            (invoice.display_name or invoice.name or str(invoice.id))
            if invoice
            else False
        )
        payment_move_labels = [move.display_name or move.name or str(move.id) for move in payment_moves]

        if invoice:
            _logger.warning(
                "POS order %s: limpiando factura borrador %s antes del cierre/manual. PaymentMoves=%s",
                order.display_name,
                invoice_label,
                payment_move_labels,
            )

        reconciled_lines = (invoice.line_ids | payment_moves.line_ids).filtered(
            lambda line: line.account_id.reconcile
            and (line.reconciled or line.matched_debit_ids or line.matched_credit_ids)
        )
        if reconciled_lines:
            reconciled_lines.remove_move_reconcile()

        posted_payment_moves = payment_moves.filtered(lambda move: move.state == "posted")
        if posted_payment_moves:
            posted_payment_moves.button_draft()

        if payments:
            payments.write({"account_move_id": False})

        order.write({"account_move": False, "state": "paid"})

        if payment_moves:
            payment_moves.unlink()

        if invoice:
            invoice.unlink()

        return {
            "invoice_label": invoice_label,
            "payment_move_labels": payment_move_labels,
        }

    def _generate_pos_order_invoice(self):
        """Backport defensivo para Odoo 18."""
        for order in self.filtered(lambda o: o.to_invoice and not o.config_id.invoice_journal_id):
            raise UserError(_("No hay un diario de facturación configurado para esta sesión del POS."))

        result = super()._generate_pos_order_invoice()

        for order in self.filtered("to_invoice"):
            invoice = order.account_move
            if not invoice:
                raise UserError(
                    _(
                        "La orden %(order)s no se validó porque no se pudo crear la factura.",
                        order=order.name,
                    )
                )
            if not order._is_invoice_fully_emitted(invoice):
                raise UserError(order._get_invoice_emission_error_message(invoice))
            try:
                order._ensure_invoice_payment_consistency()
            except UserError as err:
                _logger.warning(
                    "POS order %s: inconsistencia de pago/factura diferida para control al cierre: %s",
                    order.display_name,
                    err.name if hasattr(err, "name") else str(err),
                )

        return result
