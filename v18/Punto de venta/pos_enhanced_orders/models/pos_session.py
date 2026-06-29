# -*- coding: utf-8 -*-

import logging

from odoo import _, models, tools
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = "pos.session"

    # =========================================================================
    # Loader params (de pos_enhanced_orders)
    # =========================================================================
    def _loader_params_pos_order(self):
        res = super()._loader_params_pos_order()
        fields_ = res["search_params"].setdefault("fields", [])
        extra = [
            "invoice_name",
            "is_fiscal",
            "invoice_state",
            "invoice_state_label",
            "payment_method_names",
        ]
        for f in extra:
            if f not in fields_:
                fields_.append(f)
        return res

    def _loader_params_pos_config(self):
        params = super()._loader_params_pos_config()

        if isinstance(params, dict) and isinstance(params.get("fields"), list):
            fields_list = params["fields"]
        else:
            search_params = params.setdefault("search_params", {})
            fields_list = search_params.setdefault("fields", [])

        for field in [
            "show_ticket_col_date",
            "show_ticket_col_receipt",
            "show_ticket_col_order",
            "show_ticket_col_client",
            "show_ticket_col_cashier",
            "show_ticket_col_total",
            "show_ticket_col_state",
            "show_ticket_col_table",
            "show_ticket_col_payments",
            "show_ticket_receipt_fiscal_info",
            "show_ticket_col_invoice_state",
            "show_ticket_btn_confirm_invoice",
            "confirm_draft_invoices_on_closing",
            "auto_reconcile_pos_invoices_on_closing",
        ]:
            if field not in fields_list:
                fields_list.append(field)

        return params

    # =========================================================================
    # Draft invoice management (de pos_v19_invoice_guard)
    # =========================================================================
    def _get_orders_with_draft_invoices(self):
        self.ensure_one()
        return (
            self._get_closed_orders()
            .sudo()
            .with_company(self.company_id)
            .filtered(lambda order: order.account_move and order.account_move.state == "draft")
        )

    def _get_orders_with_posted_invoices(self):
        self.ensure_one()
        return (
            self._get_closed_orders()
            .sudo()
            .with_company(self.company_id)
            .filtered(lambda order: order.account_move and order.account_move.state == "posted")
        )

    def _get_orders_with_unpaid_posted_invoices(self):
        self.ensure_one()
        return self._get_orders_with_posted_invoices().filtered(
            lambda order: order._requires_manual_invoice_followup(order.account_move)
        )

    def _get_orders_requiring_invoice_confirmation(self):
        self.ensure_one()
        orders = self._get_orders_with_draft_invoices()
        if not self.config_id.auto_reconcile_pos_invoices_on_closing:
            orders |= self._get_orders_with_unpaid_posted_invoices()
        return orders

    def _open_draft_invoice_confirmation_wizard(
        self,
        balancing_account=False,
        amount_to_balance=0,
        bank_payment_method_diffs=None,
    ):
        self.ensure_one()
        wizard = self.env["pos.draft.invoice.confirmation.wizard"].create_from_session(
            session=self,
            balancing_account=balancing_account,
            amount_to_balance=amount_to_balance,
            bank_payment_method_diffs=bank_payment_method_diffs or {},
        )
        return wizard._get_action()

    def _handle_draft_invoices_before_close(
        self,
        balancing_account=False,
        amount_to_balance=0,
        bank_payment_method_diffs=None,
    ):
        """Activa explícitamente la lógica de facturas borrador antes del cierre."""
        self.ensure_one()
        bank_payment_method_diffs = bank_payment_method_diffs or {}
        blocking_orders = self._get_orders_requiring_invoice_confirmation()
        draft_orders = blocking_orders.filtered(lambda order: order.account_move and order.account_move.state == "draft")
        unpaid_posted_orders = blocking_orders.filtered(
            lambda order: order.account_move and order.account_move.state == "posted"
        )
        if not blocking_orders:
            return False

        if self.config_id.confirm_draft_invoices_on_closing and not self.env.context.get("skip_draft_invoice_confirmation"):
            _logger.info(
                "POS session %s: se activa el control manual de facturas POS al cierre. Borradores=%s No conciliadas=%s",
                self.display_name,
                ", ".join(draft_orders.mapped("name")) or "-",
                ", ".join(unpaid_posted_orders.mapped("name")) or "-",
            )
            return self._open_draft_invoice_confirmation_wizard(
                balancing_account=balancing_account,
                amount_to_balance=amount_to_balance,
                bank_payment_method_diffs=bank_payment_method_diffs,
            )

        _logger.info(
            "POS session %s: se reactiva la limpieza automática de facturas borrador antes del cierre para las órdenes %s",
            self.display_name,
            ", ".join(draft_orders.mapped("name")) or "-",
        )
        self._cleanup_draft_pos_invoices_before_close()
        return False

    def _validate_session(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        bank_payment_method_diffs = bank_payment_method_diffs or {}
        self.ensure_one()
        draft_result = self._handle_draft_invoices_before_close(
            balancing_account=balancing_account,
            amount_to_balance=amount_to_balance,
            bank_payment_method_diffs=bank_payment_method_diffs,
        )
        if draft_result:
            return draft_result
        return super()._validate_session(
            balancing_account=balancing_account,
            amount_to_balance=amount_to_balance,
            bank_payment_method_diffs=bank_payment_method_diffs,
        )

    def close_session_from_ui(self, bank_payment_method_diff_pairs=None):
        """Permite abrir el asistente de confirmación desde el frontend del POS."""
        bank_payment_method_diffs = dict(bank_payment_method_diff_pairs or [])
        self.ensure_one()
        open_order_ids = self.get_session_orders().filtered(lambda o: o.state == "draft").ids
        check_closing_session = self._cannot_close_session(bank_payment_method_diffs)
        if check_closing_session:
            check_closing_session["open_order_ids"] = open_order_ids
            return check_closing_session

        try:
            validate_result = self.action_pos_session_closing_control(
                bank_payment_method_diffs=bank_payment_method_diffs,
            )
        except UserError as error:
            return {
                "open_order_ids": open_order_ids,
                "successful": False,
                "redirect": False,
                "type": "alert",
                "title": _("No se pudo cerrar la sesión"),
                "message": tools.ustr(getattr(error, "name", False) or (error.args and error.args[0]) or error),
            }

        if isinstance(validate_result, dict):
            if validate_result.get("draft_invoice_confirmation_wizard"):
                return {
                    "open_order_ids": open_order_ids,
                    "successful": False,
                    "redirect": False,
                    "type": "draft_invoice_confirmation",
                    "title": validate_result.get("name") or _("Confirmación de facturas del POS"),
                    "message": _(
                        "Hay facturas del POS pendientes de regularización. Antes de cerrar la sesión tiene que emitir, eliminar o revisar manualmente las que sigan pendientes."
                    ),
                    "wizard_id": validate_result.get("res_id"),
                    "wizard_model": validate_result.get("res_model"),
                }
            return {
                "open_order_ids": open_order_ids,
                "successful": False,
                "message": validate_result.get("name"),
                "redirect": True,
            }

        self.post_close_register_message()
        return {"successful": True}

    def _cleanup_draft_pos_invoices_before_close(self):
        """Saneamiento para datos históricos ya dañados."""
        for session in self:
            orders = session._get_orders_with_draft_invoices()
            if not orders:
                continue

            order_labels = []
            invoice_labels = []
            payment_move_labels = []

            for order in orders:
                cleanup_info = order._cleanup_draft_invoice_artifacts()
                order_labels.append(order.name or str(order.id))
                if cleanup_info.get("invoice_label"):
                    invoice_labels.append(cleanup_info["invoice_label"])
                payment_move_labels.extend(cleanup_info.get("payment_move_labels") or [])

            _logger.warning(
                "POS session %s: eliminando facturas borrador del POS antes del cierre. Orders=%s Invoices=%s PaymentMoves=%s",
                session.display_name,
                order_labels,
                invoice_labels,
                payment_move_labels,
            )

            message_parts = [
                _(
                    "Se eliminaron automáticamente facturas borrador del POS antes del cierre. Órdenes: %(orders)s. Facturas: %(invoices)s",
                    orders=", ".join(order_labels),
                    invoices=", ".join(invoice_labels),
                )
            ]
            if payment_move_labels:
                message_parts.append(
                    _(
                        "También se restablecieron a borrador y eliminaron los asientos de pago POS vinculados: %(moves)s",
                        moves=", ".join(payment_move_labels),
                    )
                )

            session.message_post(body="<br/>".join(message_parts))

    def _ensure_pos_invoice_payments_before_close(self, raise_if_pending=True):
        for session in self:
            pending_orders = session._get_orders_with_posted_invoices().sudo().with_company(session.company_id).filtered(
                lambda order: order._requires_manual_invoice_followup(order.account_move)
            )
            if not pending_orders:
                continue

            errors_by_order = {}
            max_passes = 3
            committed_progress = False
            for _attempt in range(max_passes):
                next_pending = self.env["pos.order"]
                progress_made = False

                for order in pending_orders:
                    order = order.sudo().with_company(session.company_id)
                    invoice = order.account_move.sudo().with_company(session.company_id)
                    if not invoice or invoice.state != "posted":
                        continue
                    if not order._requires_manual_invoice_followup(invoice):
                        errors_by_order.pop(order.id, None)
                        continue

                    before_linked_move_ids = set(order._get_linked_pos_payment_moves().ids)
                    before_driver_move_ids = set(order._get_pos_payment_moves_drivers().mapped("account_move_id").ids)
                    before_settled = order._is_invoice_settled(invoice)

                    try:
                        with self.env.cr.savepoint():
                            order._ensure_invoice_payment_consistency()
                    except Exception as error:
                        errors_by_order[order.id] = tools.ustr(
                            getattr(error, "name", False) or (getattr(error, "args", False) and error.args[0]) or error
                        )

                    refreshed_order, refreshed_invoice = order._refresh_invoice_payment_records(invoice)
                    if refreshed_invoice and refreshed_invoice.state == "posted" and not refreshed_order._requires_manual_invoice_followup(refreshed_invoice):
                        errors_by_order.pop(order.id, None)
                        progress_made = True
                        continue

                    after_linked_move_ids = set(refreshed_order._get_linked_pos_payment_moves().ids)
                    after_driver_move_ids = set(refreshed_order._get_pos_payment_moves_drivers().mapped("account_move_id").ids)
                    after_settled = refreshed_order._is_invoice_settled(refreshed_invoice)
                    if (
                        after_linked_move_ids != before_linked_move_ids
                        or after_driver_move_ids != before_driver_move_ids
                        or after_settled != before_settled
                    ):
                        progress_made = True

                    next_pending |= refreshed_order

                pending_orders = next_pending.filtered(
                    lambda order: order.account_move and order.account_move.state == "posted" and order._requires_manual_invoice_followup(order.account_move)
                )
                if progress_made:
                    self.env.cr.flush()
                    self.env.cr.commit()
                    self.env.invalidate_all()
                    committed_progress = True
                if not pending_orders or not progress_made:
                    break

            if pending_orders:
                details = []
                for order in pending_orders:
                    invoice = order.account_move.sudo().with_company(session.company_id)
                    if not invoice or invoice.state != "posted" or not order._requires_manual_invoice_followup(invoice):
                        continue
                    details.append(
                        _(
                            "%(order)s / %(invoice)s: %(message)s",
                            order=order.display_name,
                            invoice=invoice.display_name or invoice.name or invoice.id,
                            message=errors_by_order.get(order.id) or order._get_invoice_payment_error_message(invoice),
                        )
                    )
                if details:
                    if committed_progress:
                        self.env.cr.flush()
                        self.env.cr.commit()
                        self.env.invalidate_all()
                    raise UserError(
                        _(
                            "No se pudo completar automáticamente la conciliación de todas las facturas emitidas del POS antes del cierre:\n%(details)s",
                            details="\n".join(details),
                        )
                    )

    def _check_invoices_are_posted(self):
        auto_reconcile_sessions = self.filtered(lambda session: session.config_id.auto_reconcile_pos_invoices_on_closing)
        for session in self:
            if not session.config_id.confirm_draft_invoices_on_closing:
                session._cleanup_draft_pos_invoices_before_close()
        result = super()._check_invoices_are_posted()
        if auto_reconcile_sessions:
            auto_reconcile_sessions._ensure_pos_invoice_payments_before_close()
        return result
