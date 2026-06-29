# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class L10nArPaymentRegisterMultiLine(models.TransientModel):
    _name = "l10n_ar.payment.register.multi.line"
    _description = "Línea de múltiple método de pago"

    wizard_id = fields.Many2one(
        "account.payment.register",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )

    journal_id = fields.Many2one(
        "account.journal",
        string="Diario",
        required=True,
        domain="[('type', 'in', ('bank', 'cash')), ('id', 'in', available_journal_ids)]",
    )

    available_journal_ids = fields.Many2many(
        "account.journal",
        related="wizard_id.available_journal_ids",
        readonly=True,
    )

    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Método de pago",
        required=True,
        domain="[('journal_id', '=', journal_id), ('payment_type', '=', parent.payment_type)]",
    )

    amount = fields.Monetary(
        string="Importe",
        currency_field="currency_id",
        default=0.0,
        help="Importe neto real imputado a este método de pago.",
    )

    currency_id = fields.Many2one(
        "res.currency",
        related="wizard_id.currency_id",
        readonly=True,
    )

    partner_bank_id = fields.Many2one(
        "res.partner.bank",
        string="Cuenta bancaria destinatario",
        domain="[('partner_id', '=', parent.partner_id)]",
    )

    communication = fields.Char(
        string="Memo",
    )

    x_is_check_line = fields.Boolean(
        string="Es cheque",
        compute="_compute_x_is_check_line",
        store=False,
    )

    x_ar_last_edited = fields.Boolean(
        string="Última línea editada",
        default=False,
    )

    @api.depends("payment_method_line_id.code", "payment_method_line_id.name", "journal_id")
    def _compute_x_is_check_line(self):
        for line in self:
            if line.wizard_id:
                line.x_is_check_line = bool(
                    line.wizard_id._x_ar_get_check_bucket(line.payment_method_line_id)
                )
            else:
                code = (line.payment_method_line_id.code or "") if line.payment_method_line_id else ""
                line.x_is_check_line = code in {
                    "in_third_party_checks",
                    "out_third_party_checks",
                    "return_third_party_checks",
                    "new_third_party_checks",
                    "own_checks",
                }

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        for line in self:
            if not line.journal_id:
                line.payment_method_line_id = False
                continue
            available_methods = line.journal_id._get_available_payment_method_lines(
                line.wizard_id.payment_type
            )
            line.payment_method_line_id = available_methods[:1] if available_methods else False
            # Recalcular montos de cheques por si cambia el banco del diario
            if line.wizard_id and line.wizard_id.use_multi_payment:
                line.wizard_id._x_ar_sync_multi_check_line_amounts()

    @api.onchange("payment_method_line_id")
    def _onchange_payment_method_line_id(self):
        """Cuando se cambia el método de pago:
        - Si es línea de cheque, inicializar en 0
        - Recalcular montos de todas las líneas de cheques (para filtrar por banco si hay múltiples)
        """
        for line in self:
            if not line.wizard_id or not line.wizard_id.use_multi_payment:
                continue
            if line.x_is_check_line:
                line.amount = 0.0
            # Recalcular montos de cheques (importante cuando hay múltiples líneas de cheques propios)
            line.wizard_id._x_ar_sync_multi_check_line_amounts()

    @api.constrains("amount")
    def _check_amount_non_negative(self):
        for line in self:
            if line.amount < 0:
                raise ValidationError(
                    _("El importe de la línea de pago no puede ser negativo.")
                )

    @api.onchange("amount")
    def _onchange_amount(self):
        """Marca esta línea como última editada para que el wizard
        sepa cuál línea ajustar al redistribuir montos."""
        for line in self:
            if line.wizard_id:
                # Marcar todas las líneas como no editadas
                for other in line.wizard_id.payment_line_ids:
                    other.x_ar_last_edited = False
                # Marcar esta como la última editada
                line.x_ar_last_edited = True