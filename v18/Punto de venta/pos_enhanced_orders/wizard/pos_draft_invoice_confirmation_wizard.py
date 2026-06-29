# -*- coding: utf-8 -*-

import json

from odoo import _, Command, api, fields, models, tools
from odoo.exceptions import UserError


class PosDraftInvoiceConfirmationWizard(models.TransientModel):
    _name = "pos.draft.invoice.confirmation.wizard"
    _description = "Confirmación de facturas del POS"

    session_id = fields.Many2one("pos.session", string="Sesión", required=True, readonly=True)
    session_name = fields.Char(related="session_id.name", string="Sesión", readonly=True)
    config_id = fields.Many2one(related="session_id.config_id", readonly=True)
    currency_id = fields.Many2one(related="session_id.currency_id", readonly=True)
    line_ids = fields.One2many(
        "pos.draft.invoice.confirmation.wizard.line",
        "wizard_id",
        string="Facturas del POS",
    )
    amount_to_balance = fields.Monetary(string="Importe a balancear", currency_field="currency_id", readonly=True)
    balancing_account_id = fields.Many2one("account.account", string="Cuenta de balance", readonly=True)
    bank_payment_method_diff_pairs_json = fields.Text(readonly=True)
    login_number = fields.Integer(readonly=True)
    total_count = fields.Integer(compute="_compute_counts")
    pending_count = fields.Integer(compute="_compute_counts")
    done_count = fields.Integer(compute="_compute_counts")
    error_count = fields.Integer(compute="_compute_counts")
    deleted_count = fields.Integer(compute="_compute_counts")
    can_continue = fields.Boolean(compute="_compute_can_continue")

    @api.depends("line_ids.emit_state")
    def _compute_counts(self):
        for wizard in self:
            wizard.total_count = len(wizard.line_ids)
            wizard.pending_count = len(wizard.line_ids.filtered(lambda line: line.emit_state in ("pending", "unpaid")))
            wizard.done_count = len(wizard.line_ids.filtered(lambda line: line.emit_state == "done"))
            wizard.error_count = len(wizard.line_ids.filtered(lambda line: line.emit_state == "error"))
            wizard.deleted_count = len(wizard.line_ids.filtered(lambda line: line.emit_state == "deleted"))

    @api.depends("line_ids.emit_state", "line_ids.account_move_id")
    def _compute_can_continue(self):
        for wizard in self:
            wizard.can_continue = not wizard.session_id._get_orders_requiring_invoice_confirmation()

    @api.model
    def create_from_session(self, session, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        session.ensure_one()
        bank_payment_method_diffs = bank_payment_method_diffs or {}
        balancing_account_id = getattr(balancing_account, "id", False) or False
        if isinstance(balancing_account, int):
            balancing_account_id = balancing_account

        wizard_vals = {
            "session_id": session.id,
            "amount_to_balance": amount_to_balance or 0,
            "balancing_account_id": balancing_account_id,
            "bank_payment_method_diff_pairs_json": json.dumps(list(bank_payment_method_diffs.items())),
            "login_number": int(self.env.context.get("login_number") or 0),
            "line_ids": [
                Command.create(self._prepare_line_vals_from_order(order))
                for order in session._get_orders_requiring_invoice_confirmation()
            ],
        }
        wizard = self.create(wizard_vals)
        wizard._sync_line_states()
        return wizard

    @api.model
    def _prepare_line_vals_from_order(self, order):
        invoice = order.account_move.sudo().with_company(order.company_id)
        partner_name = (
            (invoice.partner_id.display_name if invoice and invoice.partner_id else False)
            or order.partner_id.display_name
            or _("Consumidor final")
        )
        line_type = "draft"
        emit_state = "pending"
        if invoice and invoice.state == "posted" and order._requires_manual_invoice_followup(invoice):
            line_type = "unpaid_posted"
            emit_state = "unpaid"
        return {
            "pos_order_id": order.id,
            "account_move_id": invoice.id if invoice else False,
            "order_name": order.name or order.pos_reference or str(order.id),
            "invoice_name": ((invoice.display_name or invoice.name or str(invoice.id)) if invoice else False),
            "partner_name": partner_name,
            "amount_total": invoice.amount_total if invoice else order.amount_total,
            "currency_id": order.currency_id.id,
            "invoice_state": invoice.state if invoice else False,
            "invoice_state_label": order._get_invoice_state_label(invoice),
            "afip_cae": order._get_invoice_authorization_code(invoice),
            "cae_display": order._get_invoice_cae_display(invoice),
            "line_type": line_type,
            "emit_state": emit_state,
        }

    def _get_action(self):
        self.ensure_one()
        return {
            "name": _("Confirmación de facturas del POS"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": self._name,
            "res_id": self.id,
            "view_id": self.env.ref(
                "pos_enhanced_orders.pos_draft_invoice_confirmation_wizard_form_view"
            ).id,
            "target": "new",
            "context": {
                **self.env.context,
                "active_ids": self.session_id.ids,
                "active_model": "pos.session",
            },
            "draft_invoice_confirmation_wizard": True,
        }

    def _deserialize_bank_payment_method_diffs(self):
        self.ensure_one()
        raw_pairs = json.loads(self.bank_payment_method_diff_pairs_json or "[]")
        return {int(payment_method_id): amount for payment_method_id, amount in raw_pairs}

    def _sync_line_states(self):
        self.ensure_one()
        current_orders = self.session_id._get_orders_requiring_invoice_confirmation()
        current_order_ids = set(current_orders.ids)
        existing_order_ids = set(self.line_ids.mapped("pos_order_id").ids)
        if current_orders:
            missing_orders = current_orders.filtered(lambda order: order.id not in existing_order_ids)
            if missing_orders:
                self.write(
                    {
                        "line_ids": [
                            Command.create(self._prepare_line_vals_from_order(order))
                            for order in missing_orders
                        ]
                    }
                )
        for line in self.line_ids:
            line._sync_from_source()
        stale_lines = self.line_ids.filtered(lambda line: line.pos_order_id.id not in current_order_ids)
        if stale_lines:
            stale_lines.unlink()

    def action_refresh_lines(self):
        self.ensure_one()
        self._sync_line_states()
        return self._get_action()

    def action_continue_session_closing(self):
        self.ensure_one()
        self._sync_line_states()
        remaining_orders = self.session_id._get_orders_requiring_invoice_confirmation()
        if remaining_orders:
            raise UserError(
                _(
                    "Todavía hay facturas del POS pendientes para estas órdenes: %(orders)s",
                    orders=", ".join(remaining_orders.mapped("name")),
                )
            )

        if self.session_id.state == "closed":
            return {"type": "ir.actions.act_window_close"}

        result = self.session_id.with_context(
            skip_draft_invoice_confirmation=True,
            login_number=self.login_number or self.env.context.get("login_number"),
        ).action_pos_session_validate(
            balancing_account=self.balancing_account_id,
            amount_to_balance=self.amount_to_balance,
            bank_payment_method_diffs=self._deserialize_bank_payment_method_diffs(),
        )
        self.env.flush_all()
        self.env.invalidate_all()
        fresh_session = self.env["pos.session"].browse(self.session_id.id).exists()
        if fresh_session and fresh_session.state == "closed":
            return {"type": "ir.actions.act_window_close"}
        if result is True or not result:
            return {"type": "ir.actions.act_window_close"}
        return result


class PosDraftInvoiceConfirmationWizardLine(models.TransientModel):
    _name = "pos.draft.invoice.confirmation.wizard.line"
    _description = "Línea de confirmación de facturas borrador del POS"
    _order = "id"

    wizard_id = fields.Many2one(
        "pos.draft.invoice.confirmation.wizard",
        required=True,
        ondelete="cascade",
    )
    currency_id = fields.Many2one("res.currency", required=True, readonly=True)
    pos_order_id = fields.Many2one("pos.order", string="Orden", required=True, readonly=True)
    account_move_id = fields.Many2one("account.move", string="Factura", readonly=True)
    order_name = fields.Char(string="Orden", readonly=True)
    invoice_name = fields.Char(string="Factura", readonly=True)
    partner_name = fields.Char(string="Cliente", readonly=True)
    amount_total = fields.Monetary(string="Total", currency_field="currency_id", readonly=True)
    invoice_state = fields.Char(string="Estado técnico", readonly=True)
    invoice_state_label = fields.Char(string="Estado", readonly=True)
    line_type = fields.Selection(
        [
            ("draft", "Borrador"),
            ("unpaid_posted", "Registrada no conciliada"),
        ],
        string="Tipo",
        readonly=True,
        default="draft",
    )
    emit_state = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("unpaid", "No conciliado"),
            ("done", "Pagada"),
            ("error", "Error"),
            ("deleted", "Eliminada"),
        ],
        default="pending",
        readonly=True,
    )
    afip_cae = fields.Char(string="CAE", readonly=True)
    cae_display = fields.Char(string="CAE", readonly=True)
    message_display = fields.Char(string="Mensaje", compute="_compute_message_display")
    action_display = fields.Char(string="Acciones", compute="_compute_action_display")
    error_message = fields.Text(string="Detalle del error", readonly=True)
    last_attempt_at = fields.Datetime(string="Último intento", readonly=True)
    emitted_at = fields.Datetime(string="Emitida el", readonly=True)
    can_emit = fields.Boolean(compute="_compute_allowed_actions")
    can_pay = fields.Boolean(compute="_compute_allowed_actions")
    can_delete = fields.Boolean(compute="_compute_allowed_actions")
    can_view = fields.Boolean(compute="_compute_allowed_actions")
    has_error_message = fields.Boolean(compute="_compute_allowed_actions")
    has_pos_payment_drivers = fields.Boolean(compute="_compute_allowed_actions")
    payment_action_label = fields.Char(compute="_compute_allowed_actions")

    def _current_user_can_view_documents(self):
        self.ensure_one()
        return bool(
            self.env.user.has_group("base.group_system")
            or self.env.user.has_group("pos_enhanced_orders.group_pos_invoice_closing_view")
        )

    @api.depends("emit_state", "account_move_id", "error_message", "line_type")
    def _compute_allowed_actions(self):
        for line in self:
            invoice = line._get_source_invoice()
            order = line._get_source_order()
            has_payment_drivers = bool(invoice and invoice.state == "posted" and order._get_pos_payment_moves_drivers())
            line.can_emit = bool(
                line.line_type == "draft"
                and invoice
                and invoice.state == "draft"
                and line.emit_state not in ("done", "deleted")
            )
            line.can_pay = bool(
                invoice
                and invoice.state == "posted"
                and order._requires_manual_invoice_followup(invoice)
                and line.emit_state not in ("done", "deleted")
            )
            line.can_delete = bool(
                invoice and invoice.state == "draft" and line.emit_state == "error"
            )
            line.can_view = line._current_user_can_view_documents()
            line.has_error_message = bool(line.error_message)
            line.has_pos_payment_drivers = has_payment_drivers
            line.payment_action_label = _("Conciliar") if has_payment_drivers else _("Pagar")

    @api.depends("emit_state", "error_message", "line_type")
    def _compute_message_display(self):
        for line in self:
            if line.emit_state == "done":
                line.message_display = _("Pagada")
            elif line.emit_state == "deleted":
                line.message_display = _("Eliminada")
            elif line.emit_state == "error":
                line.message_display = _("Ver error")
            elif line.emit_state == "unpaid" or line.line_type == "unpaid_posted":
                line.message_display = _("No conciliado")
            else:
                line.message_display = _("Pendiente")

    @api.depends("emit_state", "can_emit", "can_pay", "can_delete", "can_view")
    def _compute_action_display(self):
        for line in self:
            line.action_display = ""

    def _get_source_order(self):
        self.ensure_one()
        return self.pos_order_id.sudo().with_company(self.wizard_id.session_id.company_id)

    def _get_source_invoice(self):
        self.ensure_one()
        order = self._get_source_order()
        invoice = order.account_move.sudo().with_company(order.company_id)
        if invoice:
            return invoice
        return self.account_move_id.sudo().with_company(order.company_id).exists()

    def _extract_exception_message(self, error):
        message = False
        if getattr(error, "name", False):
            message = error.name
        elif getattr(error, "args", False):
            message = error.args[0]
        if not message:
            message = tools.exception_to_unicode(error)
        return tools.ustr(message or _("Se produjo un error al intentar emitir la factura."))

    def _sync_from_source(self):
        self.ensure_one()
        order = self._get_source_order()
        invoice = self._get_source_invoice()
        vals = {
            "account_move_id": invoice.id if invoice else False,
            "invoice_name": (
                (invoice.display_name or invoice.name or self.invoice_name)
                if invoice
                else self.invoice_name
            ),
            "partner_name": (
                (invoice.partner_id.display_name if invoice and invoice.partner_id else False)
                or order.partner_id.display_name
                or self.partner_name
            ),
            "amount_total": invoice.amount_total if invoice else self.amount_total,
            "invoice_state": invoice.state if invoice else False,
            "invoice_state_label": order._get_invoice_state_label(invoice),
            "afip_cae": order._get_invoice_authorization_code(invoice),
            "cae_display": order._get_invoice_cae_display(invoice),
            "line_type": "unpaid_posted" if invoice and invoice.state == "posted" else "draft",
        }
        if not invoice:
            vals.update({
                "emit_state": "deleted",
                "error_message": False,
            })
        elif order._is_invoice_fully_emitted(invoice):
            if invoice.payment_state == "paid":
                vals.update({
                    "emit_state": "done",
                    "error_message": False,
                    "emitted_at": self.emitted_at or fields.Datetime.now(),
                })
            else:
                vals.update({
                    "line_type": "unpaid_posted",
                    "emit_state": "unpaid",
                    "error_message": False,
                })
        elif invoice.state != "draft":
            vals.update({
                "emit_state": "error",
                "error_message": self.error_message or order._get_invoice_emission_error_message(invoice),
            })
        self.write(vals)

    def action_view_order(self):
        self.ensure_one()
        if not self._current_user_can_view_documents():
            raise UserError(_("No tiene permisos para abrir la orden o la factura desde este asistente."))
        invoice = self._get_source_invoice()
        if invoice:
            return {
                "type": "ir.actions.act_window",
                "name": _("Factura"),
                "res_model": "account.move",
                "res_id": invoice.id,
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "new",
                "context": {"move_type": invoice.move_type},
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("Orden del POS"),
            "res_model": "pos.order",
            "res_id": self.pos_order_id.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
        }

    def action_view_error(self):
        self.ensure_one()
        if not self.error_message:
            raise UserError(_("No hay un detalle de error disponible para esta factura."))
        wizard = self.env["pos.draft.invoice.error.wizard"].create(
            {
                "order_name": self.order_name,
                "invoice_name": self.invoice_name,
                "last_attempt_at": self.last_attempt_at,
                "error_message": self.error_message,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Detalle del error"),
            "res_model": "pos.draft.invoice.error.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "views": [(
                self.env.ref("pos_enhanced_orders.pos_draft_invoice_error_wizard_form_view").id,
                "form",
            )],
            "target": "new",
        }

    def action_pay_invoice(self):
        self.ensure_one()
        self._sync_from_source()
        order = self._get_source_order()
        invoice = self._get_source_invoice()
        now = fields.Datetime.now()

        if not invoice or invoice.state != "posted":
            raise UserError(_("Solo se pueden pagar o conciliar facturas que ya estén registradas."))

        if invoice.payment_state == "paid":
            self.write({
                "emit_state": "done",
                "error_message": False,
                "last_attempt_at": now,
                "emitted_at": self.emitted_at or now,
            })
            return False

        driver_payments = order._get_pos_payment_moves_drivers()
        if driver_payments:
            try:
                with self.env.cr.savepoint():
                    order._ensure_invoice_payment_consistency()
            except Exception as error:
                self._sync_from_source()
                self.write(
                    {
                        "emit_state": "unpaid",
                        "error_message": self._extract_exception_message(error),
                        "last_attempt_at": now,
                    }
                )
                raise UserError(
                    _(
                        "No se pudo conciliar la factura %(invoice)s con los asientos de pago del POS ya existentes.",
                        invoice=invoice.display_name or invoice.name,
                    )
                )

            self._sync_from_source()
            invoice = self._get_source_invoice()
            if invoice and invoice.payment_state == "paid":
                self.write({
                    "emit_state": "done",
                    "error_message": False,
                    "last_attempt_at": now,
                    "emitted_at": self.emitted_at or now,
                })
                return False

            raise UserError(order._get_invoice_payment_error_message(invoice))

        self.write({
            "emit_state": "unpaid",
            "error_message": False,
            "last_attempt_at": now,
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Registrar pago"),
            "res_model": "account.payment.register",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "active_model": "account.move",
                "active_ids": invoice.ids,
                "active_id": invoice.id,
                "default_communication": invoice.name or invoice.ref or invoice.display_name,
            },
        }

    def action_emit_invoice(self):
        self.ensure_one()
        self._sync_from_source()
        order = self._get_source_order()
        now = fields.Datetime.now()

        if not self.can_emit:
            invoice = self._get_source_invoice()
            if invoice and order._is_invoice_fully_emitted(invoice) and not order._requires_manual_invoice_followup(invoice):
                self.write({"emit_state": "done", "error_message": False, "emitted_at": self.emitted_at or now})
                return False
            raise UserError(_("Solo se pueden emitir facturas que sigan en borrador."))

        try:
            with self.env.cr.savepoint():
                invoice = self._get_source_invoice()
                if not invoice:
                    raise UserError(_("La orden ya no tiene una factura asociada."))
                if invoice.state != "draft":
                    raise UserError(_("La factura ya no está en borrador."))
                invoice.action_post()
                invoice = self._get_source_invoice()
                if not order._is_invoice_fully_emitted(invoice):
                    raise UserError(order._get_invoice_emission_error_message(invoice))
                if order.state not in ("invoiced", "done"):
                    order.write({"state": "invoiced"})
        except Exception as error:
            self._sync_from_source()
            self.write(
                {
                    "emit_state": "error",
                    "error_message": self._extract_exception_message(error),
                    "last_attempt_at": now,
                }
            )
        else:
            invoice = self._get_source_invoice()
            invoice_paid = bool(invoice and invoice.payment_state == "paid")
            self.write(
                {
                    "emit_state": "done" if invoice_paid else "unpaid",
                    "line_type": "unpaid_posted" if invoice and invoice.state == "posted" and not invoice_paid else self.line_type,
                    "error_message": False,
                    "last_attempt_at": now,
                    "emitted_at": now,
                    "account_move_id": invoice.id if invoice else False,
                    "invoice_name": ((invoice.display_name or invoice.name or self.invoice_name) if invoice else self.invoice_name),
                    "invoice_state": invoice.state if invoice else False,
                    "invoice_state_label": order._get_invoice_state_label(invoice),
                    "afip_cae": order._get_invoice_authorization_code(invoice),
                    "cae_display": order._get_invoice_cae_display(invoice),
                }
            )
        return False

    def action_delete_draft_invoice(self):
        self.ensure_one()
        self._sync_from_source()
        invoice = self._get_source_invoice()
        now = fields.Datetime.now()
        if not invoice or invoice.state != "draft":
            raise UserError(_("Solo se pueden eliminar facturas que sigan en borrador."))

        try:
            with self.env.cr.savepoint():
                self._get_source_order()._cleanup_draft_invoice_artifacts()
        except Exception as error:
            self._sync_from_source()
            self.write(
                {
                    "emit_state": "error",
                    "error_message": self._extract_exception_message(error),
                    "last_attempt_at": now,
                }
            )
        else:
            self.write(
                {
                    "emit_state": "deleted",
                    "error_message": False,
                    "last_attempt_at": now,
                    "account_move_id": False,
                    "invoice_state": False,
                    "invoice_state_label": False,
                    "afip_cae": False,
                    "cae_display": False,
                }
            )
        return False
