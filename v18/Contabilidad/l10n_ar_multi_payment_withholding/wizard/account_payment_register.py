# -*- coding: utf-8 -*-
import json
from uuid import uuid4

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    use_multi_payment = fields.Boolean(
        string="Utilice múltiples métodos de pago",
        default=False,
    )

    payment_line_ids = fields.One2many(
        "l10n_ar.payment.register.multi.line",
        "wizard_id",
        string="Líneas de pago",
    )

    x_ar_auto_calculate = fields.Boolean(
        string="Cálculo automático",
        default=False,
        help="Si está activo, redistribuye automáticamente los importes de las líneas "
             "para que el total coincida con el neto a cubrir.",
    )

    # Flag interno para evitar re-entrada en el recompute
    x_ar_recomputing = fields.Boolean(default=False, store=False)

    x_ar_apply_withholdings = fields.Boolean(
        string="Aplicar retenciones",
        default=lambda self: self.env.company.country_code == "AR",
        help="Si está activo, se habilita la solapa de Retenciones y se descuenta "
             "su impacto del total a cubrir con medios de pago.",
    )

    x_ar_gross_amount = fields.Monetary(
        string="Total documento / pago base",
        currency_field="currency_id",
        compute="_compute_x_ar_gross_amount",
        store=False,
        help="Monto bruto fijo del documento a cancelar. No debe variar por el importe del cheque.",
    )

    x_ar_withholding_total = fields.Monetary(
        string="Total retenciones",
        currency_field="currency_id",
        compute="_compute_x_ar_usability_amounts",
        store=False,
    )

    x_ar_document_total_amount = fields.Monetary(
        string="Total documento / pago base",
        currency_field="currency_id",
        compute="_compute_x_ar_usability_amounts",
        store=False,
    )

    x_ar_payment_instrument_amount = fields.Monetary(
        string="Importe real del medio de pago",
        currency_field="currency_id",
        compute="_compute_x_ar_usability_amounts",
        store=False,
    )

    x_ar_check_amount_total = fields.Monetary(
        string="Importe de cheques",
        currency_field="currency_id",
        compute="_compute_x_ar_usability_amounts",
        store=False,
    )

    x_ar_is_check_payment = fields.Boolean(
        string="Usa cheques",
        compute="_compute_x_ar_usability_amounts",
        store=False,
    )

    x_ar_checks_match_net = fields.Boolean(
        string="Cheque coincide con neto",
        compute="_compute_x_ar_usability_amounts",
        store=False,
    )

    x_ar_checks_cover_net = fields.Boolean(
        string="Cheques cubren el neto",
        compute="_compute_x_ar_usability_amounts",
        store=False,
        help="True si el total de cheques es >= al neto a pagar. "
             "Permite pagos con cheques de mayor valor (la diferencia queda como anticipo).",
    )

    x_ar_multi_total = fields.Monetary(
        string="Total líneas de pago",
        currency_field="currency_id",
        compute="_compute_x_ar_multi_amounts",
        store=False,
    )

    x_ar_multi_target_amount = fields.Monetary(
        string="Total a cubrir con medios de pago",
        currency_field="currency_id",
        compute="_compute_x_ar_multi_amounts",
        store=False,
    )

    x_ar_multi_difference = fields.Monetary(
        string="Diferencia",
        currency_field="currency_id",
        compute="_compute_x_ar_multi_amounts",
        store=False,
    )

    x_ar_multi_is_balanced = fields.Boolean(
        string="Múltiple pago balanceado",
        compute="_compute_x_ar_multi_amounts",
        store=False,
    )

    # --- Campos para tipo de cambio de factura ---
    x_ar_is_foreign_currency_invoice = fields.Boolean(
        string="Factura en moneda extranjera",
        compute="_compute_x_ar_invoice_exchange_rate",
        store=False,
    )

    x_ar_invoice_exchange_rate = fields.Float(
        string="Tipo de cambio (factura)",
        digits=(16, 6),
        compute="_compute_x_ar_invoice_exchange_rate",
        store=False,
        help="Tipo de cambio calculado desde la factura original.",
    )

    x_ar_invoice_converted_amount = fields.Monetary(
        string="Importe convertido (TC factura)",
        currency_field="company_currency_id",
        compute="_compute_x_ar_invoice_exchange_rate",
        store=False,
        help="Importe de la factura convertido usando el tipo de cambio original de la factura.",
    )

    x_ar_exchange_rate_difference = fields.Monetary(
        string="Diferencia por tipo de cambio",
        currency_field="company_currency_id",
        compute="_compute_x_ar_exchange_rate_difference",
        store=False,
        help="Diferencia entre el importe calculado con TC del día vs TC de la factura. Solo informativo.",
    )

    x_ar_has_multi_check_line = fields.Boolean(
        string="Tiene línea de cheque en múltiple pago",
        compute="_compute_x_ar_has_multi_check_line",
        store=False,
    )

    x_ar_multi_has_new_checks = fields.Boolean(
        string="Multi pago con cheques nuevos",
        compute="_compute_x_ar_multi_check_modes",
        store=False,
    )

    x_ar_multi_has_existing_checks = fields.Boolean(
        string="Multi pago con cheques existentes",
        compute="_compute_x_ar_multi_check_modes",
        store=False,
    )

    x_ar_multi_existing_check_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Diario de cheques de terceros (multi)",
        compute="_compute_x_ar_multi_existing_check_journal_id",
        store=False,
    )

    @api.depends("payment_line_ids.journal_id", "payment_line_ids.payment_method_line_id.code")
    def _compute_x_ar_multi_existing_check_journal_id(self):
        """Obtiene el diario de la línea de cheques de terceros existentes en multi-pago."""
        for wizard in self:
            journal = False
            if wizard.use_multi_payment:
                for line in wizard.payment_line_ids:
                    code = line.payment_method_line_id.code or ""
                    if code in ("in_third_party_checks", "out_third_party_checks", "return_third_party_checks"):
                        journal = line.journal_id
                        break
            wizard.x_ar_multi_existing_check_journal_id = journal

    @api.depends("use_multi_payment", "payment_line_ids.payment_method_line_id.code")
    def _compute_x_ar_multi_check_modes(self):
        for wizard in self:
            codes = set(wizard.payment_line_ids.mapped("payment_method_line_id.code"))
            wizard.x_ar_multi_has_new_checks = bool(
                wizard.use_multi_payment and codes.intersection({"new_third_party_checks", "own_checks"})
            )
            wizard.x_ar_multi_has_existing_checks = bool(
                wizard.use_multi_payment and codes.intersection({
                    "in_third_party_checks",
                    "out_third_party_checks",
                    "return_third_party_checks",
                })
            )

    @api.depends("use_multi_payment", "payment_line_ids.payment_method_line_id")
    def _compute_x_ar_has_multi_check_line(self):
        for wizard in self:
            wizard.x_ar_has_multi_check_line = bool(
                wizard.use_multi_payment
                and wizard.payment_line_ids.filtered(lambda l: wizard._is_latam_check_line(l))
            )

    @api.depends(
        "line_ids.move_id",
        "line_ids.currency_id",
        "line_ids.amount_residual",
        "line_ids.amount_residual_currency",
        "currency_id",
        "company_currency_id",
    )
    def _compute_x_ar_invoice_exchange_rate(self):
        """Calcula el tipo de cambio real usado en la factura.
        
        Esto es importante cuando la factura se registró con un TC específico
        y el wizard de pago debería respetar ese TC, no el del día del pago.
        """
        for wizard in self:
            wizard.x_ar_is_foreign_currency_invoice = False
            wizard.x_ar_invoice_exchange_rate = 1.0
            wizard.x_ar_invoice_converted_amount = 0.0

            if not wizard.line_ids:
                continue

            company_currency = wizard.company_currency_id
            if not company_currency:
                continue

            # Obtener las facturas involucradas
            moves = wizard.line_ids.mapped("move_id")
            if not moves:
                continue

            # Verificar si hay facturas en moneda extranjera
            foreign_moves = moves.filtered(
                lambda m: m.currency_id and m.currency_id != company_currency
            )
            
            if not foreign_moves:
                # No hay facturas en moneda extranjera
                wizard.x_ar_invoice_converted_amount = abs(wizard.source_amount or 0.0)
                continue

            wizard.x_ar_is_foreign_currency_invoice = True

            # Calcular el TC desde las líneas de la factura
            # Usamos las líneas del asiento para obtener el TC real usado
            total_foreign = 0.0
            total_company = 0.0

            for move in foreign_moves:
                # Buscar líneas de la factura que tengan moneda extranjera
                for line in move.line_ids:
                    if line.currency_id and line.currency_id != company_currency:
                        if line.amount_currency and line.balance:
                            total_foreign += abs(line.amount_currency)
                            total_company += abs(line.balance)

            if total_foreign and total_company:
                # TC = cuántos ARS por cada unidad de moneda extranjera
                exchange_rate = total_company / total_foreign
                wizard.x_ar_invoice_exchange_rate = exchange_rate

                # Calcular el importe pendiente convertido con el TC de la factura
                # Sumamos los residuales en moneda extranjera y los convertimos
                total_residual_foreign = 0.0
                total_residual_company = 0.0
                
                for line in wizard.line_ids:
                    if line.currency_id and line.currency_id != company_currency:
                        total_residual_foreign += abs(line.amount_residual_currency)
                    else:
                        total_residual_company += abs(line.amount_residual)

                # Convertir el residual en moneda extranjera usando el TC de la factura
                converted_amount = (total_residual_foreign * exchange_rate) + total_residual_company
                wizard.x_ar_invoice_converted_amount = converted_amount
            else:
                wizard.x_ar_invoice_converted_amount = abs(wizard.source_amount or 0.0)

    @api.depends(
        "x_ar_is_foreign_currency_invoice",
        "x_ar_invoice_converted_amount",
        "source_amount",
        "currency_id",
        "company_currency_id",
    )
    def _compute_x_ar_exchange_rate_difference(self):
        """Calcula la diferencia por tipo de cambio (solo informativo).
        
        Es la diferencia entre lo que Odoo calcularía con el TC del día
        vs lo que realmente corresponde pagar según el TC de la factura.
        """
        for wizard in self:
            wizard.x_ar_exchange_rate_difference = 0.0
            
            if not wizard.x_ar_is_foreign_currency_invoice:
                continue
            
            if wizard.currency_id != wizard.company_currency_id:
                continue
            
            # source_amount es lo que Odoo calcula con TC del día
            odoo_amount = abs(wizard.source_amount or 0.0)
            # x_ar_invoice_converted_amount es con TC de la factura
            invoice_amount = wizard.x_ar_invoice_converted_amount or 0.0
            
            if odoo_amount and invoice_amount:
                wizard.x_ar_exchange_rate_difference = odoo_amount - invoice_amount

    @api.depends(
        "source_amount",
        "source_currency_id",
        "company_id",
        "currency_id",
        "amount",
        "payment_type",
        "x_ar_is_foreign_currency_invoice",
        "x_ar_invoice_converted_amount",
        "company_currency_id",
        "l10n_latam_move_check_ids.amount",
        "l10n_latam_new_check_ids.amount",
        "x_ar_is_check_payment",
    )
    def _compute_payment_difference(self):
        """Override para usar el TC de la factura en lugar del TC del día."""
        super()._compute_payment_difference()
        
        for wizard in self:
            # Solo modificar si es factura en moneda extranjera y pago en ARS
            if not wizard.x_ar_is_foreign_currency_invoice:
                continue
            
            if wizard.currency_id != wizard.company_currency_id:
                continue
            
            # Importe de la factura con TC correcto
            invoice_amount = wizard.x_ar_invoice_converted_amount or 0.0
            
            # Importe del pago: usar suma de cheques si hay, sino amount
            if wizard.x_ar_is_check_payment:
                checks = wizard._x_ar_get_current_checks()
                payment_amount = sum(checks.mapped("amount")) if checks else 0.0
            else:
                payment_amount = wizard.amount or 0.0
            
            if wizard.payment_type == 'outbound':
                # Pago a proveedor: diferencia = factura - pago
                wizard.payment_difference = invoice_amount - payment_amount
            else:
                # Cobro de cliente: diferencia = pago - factura
                wizard.payment_difference = payment_amount - invoice_amount

    @api.depends(
        "source_amount",
        "source_amount_currency",
        "line_ids.amount_residual",
        "line_ids.amount_residual_currency",
        "line_ids.currency_id",
        "currency_id",
        "x_ar_invoice_converted_amount",
        "x_ar_is_foreign_currency_invoice",
    )
    def _compute_x_ar_gross_amount(self):
        for wizard in self:
            # Si hay factura en moneda extranjera, usar el importe convertido con TC de factura
            if wizard.x_ar_is_foreign_currency_invoice and wizard.x_ar_invoice_converted_amount:
                wizard.x_ar_gross_amount = wizard.x_ar_invoice_converted_amount
                continue

            gross_amount = abs(wizard.source_amount or 0.0)

            if not gross_amount:
                total = 0.0
                for line in wizard.line_ids:
                    if wizard.currency_id and line.currency_id == wizard.currency_id:
                        total += abs(line.amount_residual_currency)
                    else:
                        total += abs(line.amount_residual)
                gross_amount = total

            wizard.x_ar_gross_amount = gross_amount

    @api.depends(
        "x_ar_gross_amount",
        "l10n_ar_withholding_ids.amount",
        "l10n_ar_withholding_ids.x_manual_amount_value",
        "l10n_latam_move_check_ids.amount",
        "l10n_latam_new_check_ids.amount",
        "payment_method_code",
        "currency_id",
    )
    def _compute_x_ar_usability_amounts(self):
        for wizard in self:
            checks = wizard._x_ar_get_current_checks()
            checks_amount = sum(checks.mapped("amount"))

            # Usar x_manual_amount_value si el usuario lo modificó,
            # sino usar el amount calculado automáticamente
            withholding_total = 0.0
            for wth in wizard.l10n_ar_withholding_ids:
                if wth.x_manual_amount_value:
                    withholding_total += wth.x_manual_amount_value
                else:
                    withholding_total += wth.amount

            net_amount = wizard.x_ar_gross_amount - withholding_total

            wizard.x_ar_withholding_total = withholding_total
            wizard.x_ar_document_total_amount = wizard.x_ar_gross_amount
            wizard.x_ar_payment_instrument_amount = net_amount
            wizard.x_ar_check_amount_total = checks_amount
            wizard.x_ar_is_check_payment = bool(checks)
            wizard.x_ar_checks_match_net = (
                True if not checks
                else wizard.currency_id.compare_amounts(checks_amount, net_amount) == 0
            )
            # Cheques cubren el neto si son >= (permite cheques de mayor valor)
            wizard.x_ar_checks_cover_net = (
                True if not checks
                else wizard.currency_id.compare_amounts(checks_amount, net_amount) >= 0
            )

    @api.depends(
        "use_multi_payment",
        "payment_line_ids.amount",
        "x_ar_payment_instrument_amount",
        "amount",
        "country_code",
        "l10n_ar_withholding_ids.amount",
    )
    def _compute_x_ar_multi_amounts(self):
        for wizard in self:
            total_lines = sum(wizard.payment_line_ids.mapped("amount"))
            if wizard.country_code == "AR" and wizard.l10n_ar_withholding_ids:
                target = wizard.x_ar_payment_instrument_amount
            else:
                target = wizard.amount

            wizard.x_ar_multi_total = total_lines
            wizard.x_ar_multi_target_amount = target
            wizard.x_ar_multi_difference = target - total_lines
            wizard.x_ar_multi_is_balanced = (
                True if not wizard.currency_id
                else wizard.currency_id.is_zero(target - total_lines)
            )

    def _x_ar_get_current_checks(self):
        self.ensure_one()
        if self._is_latam_check_payment(check_subtype="new_check"):
            return self.l10n_latam_new_check_ids
        return self.l10n_latam_move_check_ids
    
    def _x_ar_should_use_custom_single_payment(self):
        """Determina si debe usar el flujo personalizado de pago simple.
        Se activa cuando:
        - Hay retenciones activas, O
        - Es un pago con cheques (para manejar correctamente el monto)
        """
        self.ensure_one()
        has_withholdings = bool(
            self.x_ar_apply_withholdings
            and self._x_ar_get_active_withholdings()
        )
        is_check_payment = self.x_ar_is_check_payment
        
        return bool(
            not self.use_multi_payment
            and self.country_code == "AR"
            and (has_withholdings or is_check_payment)
        )

    @api.depends(
        "can_edit_wizard",
        "source_amount",
        "source_amount_currency",
        "source_currency_id",
        "company_id",
        "currency_id",
        "company_currency_id",
        "payment_date",
        "installments_mode",
        "l10n_latam_move_check_ids.amount",
        "l10n_latam_new_check_ids.amount",
        "payment_method_code",
        "x_ar_gross_amount",
        "l10n_ar_withholding_ids.amount",
        "use_multi_payment",
        "x_ar_is_foreign_currency_invoice",
        "x_ar_invoice_converted_amount",
    )
    def _compute_amount(self):
        super()._compute_amount()

        for wizard in self:
            if wizard.country_code != "AR":
                continue

            # NO forzamos amount al importe de la factura.
            # amount debe reflejar el medio de pago (cheques, transferencia, etc.)
            # Solo ajustamos si amount excede el gross_amount (para evitar sobrepagos no deseados)
            gross_amount = wizard.x_ar_gross_amount or 0.0
            if gross_amount and wizard.amount and wizard.amount > gross_amount:
                # Solo limitar si NO es pago con cheques (los cheques pueden exceder)
                if not wizard.x_ar_is_check_payment:
                    wizard.amount = gross_amount

    @api.depends("x_ar_gross_amount", "l10n_ar_withholding_ids.amount", "l10n_ar_withholding_ids.x_manual_amount_value")
    def _compute_l10n_ar_net_amount(self):
        for wizard in self:
            withholding_total = 0.0
            for wth in wizard.l10n_ar_withholding_ids:
                if wth.x_manual_amount_value:
                    withholding_total += wth.x_manual_amount_value
                else:
                    withholding_total += wth.amount
            wizard.l10n_ar_net_amount = wizard.x_ar_gross_amount - withholding_total

    @api.depends(
        "l10n_ar_net_amount",
        "l10n_latam_move_check_ids.amount",
        "l10n_latam_new_check_ids.amount",
        "payment_method_code",
        "currency_id",
    )
    def _compute_l10n_ar_adjustment_warning(self):
        for wizard in self:
            checks = wizard._x_ar_get_current_checks()
            checks_amount = sum(checks.mapped("amount"))
            wizard.l10n_ar_adjustment_warning = (
                not wizard.currency_id.is_zero(checks_amount)
                and wizard.currency_id.compare_amounts(checks_amount, wizard.l10n_ar_net_amount) != 0
            )

    @api.onchange("use_multi_payment")
    def _onchange_use_multi_payment(self):
        for wizard in self:
            wizard.payment_line_ids = [Command.clear()]
            wizard.l10n_latam_new_check_ids = [Command.clear()]
            wizard.l10n_latam_move_check_ids = [Command.clear()]

            if wizard.use_multi_payment and wizard.journal_id and wizard.payment_method_line_id:
                wizard.payment_line_ids = [Command.create({
                    "journal_id": wizard.journal_id.id,
                    "payment_method_line_id": wizard.payment_method_line_id.id,
                    "amount": 0.0,
                    "communication": wizard.communication,
                })]

    def _get_latam_check_codes(self):
        return {
            "in_third_party_checks",
            "out_third_party_checks",
            "return_third_party_checks",
            "new_third_party_checks",
            "own_checks",
        }

    def _x_ar_get_check_bucket(self, payment_method_line):
        """Detecta el tipo de cheque por code o por nombre del método."""
        self.ensure_one()
        if not payment_method_line:
            return False
        code = (payment_method_line.code or "").lower()
        name = " ".join(
            x for x in [payment_method_line.display_name, payment_method_line.name] if x
        ).lower()
        if code in {"new_third_party_checks", "own_checks"} or "propio" in name or "propios" in name:
            return "new"
        if code in {"in_third_party_checks", "out_third_party_checks", "return_third_party_checks"} or "tercero" in name or "terceros" in name:
            return "move"
        return False

    def _is_latam_check_line(self, line):
        return bool(self._x_ar_get_check_bucket(line.payment_method_line_id))

    def _x_ar_get_active_withholdings(self):
        self.ensure_one()
        return self.l10n_ar_withholding_ids if self.x_ar_apply_withholdings else self.env["l10n_ar.payment.register.withholding"]

    def _x_ar_get_withholding_total_value(self):
        self.ensure_one()
        total = 0.0
        for wth in self._x_ar_get_active_withholdings():
            total += wth.x_manual_amount_value if wth.x_manual_amount_value else wth.amount
        return total

    def _x_ar_get_multi_target_amount_value(self):
        self.ensure_one()
        if self.country_code == "AR" and self.x_ar_apply_withholdings and self._x_ar_get_active_withholdings():
            return self.x_ar_payment_instrument_amount
        return self.x_ar_gross_amount or self.amount

    def _x_ar_get_effective_multi_lines(self):
        self.ensure_one()
        return self.payment_line_ids.filtered(lambda l: l.journal_id and l.payment_method_line_id)

    def _x_ar_get_check_total_for_method(self, payment_method_line, journal=None, require_bank_match=False):
        """Obtiene el total de cheques para un método de pago, filtrado por banco del diario.
        
        Args:
            payment_method_line: Método de pago
            journal: Diario para filtrar por banco
            require_bank_match: Si True y el diario no tiene banco, devuelve 0
        """
        self.ensure_one()
        bucket = self._x_ar_get_check_bucket(payment_method_line)
        
        if bucket == "new":
            checks = self.l10n_latam_new_check_ids
            # Si se requiere filtrar por banco
            if journal and require_bank_match:
                journal_bank = journal.bank_account_id.bank_id if journal.bank_account_id else False
                if not journal_bank:
                    # Si el diario no tiene banco configurado, no asignar cheques
                    return 0.0
                # Filtrar cheques por el banco del diario
                checks = checks.filtered(lambda c: c.bank_id and c.bank_id.id == journal_bank.id)
            return sum(checks.mapped("amount"))
        
        if bucket == "move":
            return sum(self.l10n_latam_move_check_ids.mapped("amount"))
        
        return 0.0

    def _x_ar_set_line_amount(self, line, amount):
        line.amount = max(amount, 0.0)

    def _x_ar_get_payment_line_share_key(self, line):
        self.ensure_one()
        return line._origin.id or line.id or id(line)

    def _x_ar_match_multi_line(self, lines, candidate):
        self.ensure_one()
        if not candidate:
            return lines.browse()
        try:
            direct = lines.filtered(lambda l: l == candidate)[:1]
            if direct:
                return direct
        except Exception:
            pass
        if getattr(candidate, "id", False):
            by_id = lines.filtered(lambda l: l.id == candidate.id)[:1]
            if by_id:
                return by_id
        if getattr(candidate, "_origin", False) and candidate._origin.id:
            by_origin = lines.filtered(lambda l: l._origin.id == candidate._origin.id)[:1]
            if by_origin:
                return by_origin
        candidate_key = self._x_ar_get_payment_line_share_key(candidate)
        return lines.filtered(lambda l: self._x_ar_get_payment_line_share_key(l) == candidate_key)[:1]

    def _x_ar_guess_edited_multi_line(self, lines=None):
        self.ensure_one()
        lines = lines or self._x_ar_get_effective_multi_lines()
        if not lines:
            return lines.browse()

        # 1. Línea marcada explícitamente como editada por el usuario
        flagged = lines.filtered(lambda l: getattr(l, "x_ar_last_edited", False))
        if flagged:
            return flagged[:1]

        currency = self.currency_id or self.company_id.currency_id

        # 2. Línea recién agregada con importe > 0 (el usuario la completó manualmente)
        new_with_amount = lines.filtered(
            lambda l: not l._origin.id and currency and not currency.is_zero(l.amount or 0.0)
        )
        if len(new_with_amount) == 1:
            return new_with_amount[:1]
        if new_with_amount:
            return new_with_amount[-1:]

        # 3. Línea recién agregada con importe = 0: es la nueva línea vacía.
        # En este caso NO la marcamos como editada — la tratamos como "línea a completar"
        # devolviendo vacío para que _redistribute le asigne el saldo restante.
        new_zero = lines.filtered(lambda l: not l._origin.id)
        if new_zero:
            return lines.browse()  # sin edited_line → _redistribute cubre todas las non-check

        return lines.browse()

    def _x_ar_recompute_multi_line_amounts(self, edited_line=None):
        for wizard in self:
            if not wizard.use_multi_payment or not wizard.x_ar_auto_calculate or not wizard.payment_line_ids:
                continue
            if wizard.x_ar_recomputing:
                continue
            wizard.x_ar_recomputing = True
            try:
                target = wizard._x_ar_get_multi_target_amount_value()
                lines = wizard._x_ar_get_effective_multi_lines()
                if not lines:
                    continue

                currency = wizard.currency_id or wizard.company_id.currency_id
                check_lines = lines.filtered(lambda l: wizard._is_latam_check_line(l))
                non_check_lines = lines - check_lines

                # Fijar importes de líneas de cheque desde los cheques cargados
                fixed_total = 0.0
                new_check_lines_in_loop = check_lines.filtered(
                    lambda l: l.payment_method_line_id.code in {"new_third_party_checks", "own_checks"}
                )
                multiple_new_check_lines = len(new_check_lines_in_loop) > 1
                for check_line in check_lines:
                    # Si hay múltiples líneas de cheques propios, filtrar por banco del diario
                    if multiple_new_check_lines and check_line in new_check_lines_in_loop:
                        check_amount = wizard._x_ar_get_check_total_for_method(
                            check_line.payment_method_line_id,
                            journal=check_line.journal_id,
                            require_bank_match=True
                        )
                    else:
                        check_amount = wizard._x_ar_get_check_total_for_method(check_line.payment_method_line_id)
                    wizard._x_ar_set_line_amount(check_line, check_amount)
                    fixed_total += check_amount

                if not non_check_lines:
                    continue

                # Detectar líneas nuevas con $0 (recién agregadas sin valor)
                new_zero_lines = non_check_lines.filtered(
                    lambda l: not l._origin.id and (not l.amount or (currency and currency.is_zero(l.amount)))
                )

                # Identificar la línea que editó el usuario
                edited_non_check = wizard._x_ar_match_multi_line(non_check_lines, edited_line)
                if not edited_non_check:
                    edited_non_check = wizard._x_ar_guess_edited_multi_line(non_check_lines)
                edited_non_check = edited_non_check[:1]

                def _redistribute(lines_to_adjust, amount_to_cover):
                    lines_to_adjust = lines_to_adjust.filtered(lambda l: l.journal_id and l.payment_method_line_id)
                    if not lines_to_adjust:
                        return
                    if len(lines_to_adjust) == 1:
                        wizard._x_ar_set_line_amount(lines_to_adjust[0], amount_to_cover)
                        return
                    current_total = sum(lines_to_adjust.mapped("amount"))
                    remaining = amount_to_cover
                    for idx, line in enumerate(lines_to_adjust):
                        if idx == len(lines_to_adjust) - 1:
                            share = remaining
                        elif currency and not currency.is_zero(current_total):
                            share = currency.round(amount_to_cover * line.amount / current_total)
                            remaining -= share
                        else:
                            share = 0.0
                        wizard._x_ar_set_line_amount(line, share)

                if new_zero_lines and not edited_non_check:
                    existing_lines = non_check_lines.filtered(lambda l: l._origin.id or (currency and not currency.is_zero(l.amount or 0.0)))
                    existing_total = sum(existing_lines.mapped("amount"))
                    remainder = target - fixed_total - existing_total
                    _redistribute(new_zero_lines, remainder)
                elif edited_non_check:
                    other_non_check = non_check_lines.filtered(lambda l: l != edited_non_check)
                    amount_to_cover = target - fixed_total - edited_non_check.amount
                    _redistribute(other_non_check, amount_to_cover)
                else:
                    _redistribute(non_check_lines, target - fixed_total)
            finally:
                wizard.x_ar_recomputing = False

    def _x_ar_sync_multi_check_line_amounts(self):
        for wizard in self.filtered("use_multi_payment"):
            check_lines = wizard.payment_line_ids.filtered(lambda l: wizard._is_latam_check_line(l))
            new_check_lines = check_lines.filtered(
                lambda l: l.payment_method_line_id.code in {"new_third_party_checks", "own_checks"}
            )
            multiple_new_check_lines = len(new_check_lines) > 1
            
            for check_line in check_lines:
                # Si hay múltiples líneas de cheques propios, filtrar por banco del diario
                if multiple_new_check_lines and check_line in new_check_lines:
                    check_amount = wizard._x_ar_get_check_total_for_method(
                        check_line.payment_method_line_id,
                        journal=check_line.journal_id,
                        require_bank_match=True
                    )
                else:
                    check_amount = wizard._x_ar_get_check_total_for_method(check_line.payment_method_line_id)
                wizard._x_ar_set_line_amount(check_line, check_amount)

    @api.onchange("x_ar_auto_calculate")
    def _onchange_x_ar_refresh_multi_lines(self):
        if self.env.context.get("x_ar_skip_multi_auto_amount_onchange"):
            return
        for wizard in self.filtered(lambda w: w.use_multi_payment and w.x_ar_auto_calculate):
            wizard._x_ar_recompute_multi_line_amounts()

    @api.onchange("x_ar_apply_withholdings", "l10n_ar_withholding_ids")
    def _onchange_x_ar_withholdings_recompute(self):
        for wizard in self:
            if not wizard.use_multi_payment or not wizard.x_ar_auto_calculate or not wizard.payment_line_ids:
                continue
            lines = wizard._x_ar_get_effective_multi_lines()
            non_check_lines = lines.filtered(lambda l: not wizard._is_latam_check_line(l))
            if not non_check_lines:
                continue
            if len(non_check_lines) == 1:
                wizard._x_ar_recompute_multi_line_amounts(edited_line=None)
            else:
                edited_line = non_check_lines.filtered(
                    lambda l: getattr(l, "x_ar_last_edited", False)
                )[:1] or None
                wizard._x_ar_recompute_multi_line_amounts(edited_line=edited_line)

    @api.onchange("l10n_latam_new_check_ids", "l10n_latam_move_check_ids")
    def _onchange_latam_check_lines(self):
        for wizard in self.filtered("use_multi_payment"):
            for line in wizard.payment_line_ids:
                line.x_ar_last_edited = False
            wizard._x_ar_sync_multi_check_line_amounts()
            wizard._x_ar_recompute_multi_line_amounts()

    def _validate_multi_payment(self):
        self.ensure_one()

        if not self.use_multi_payment:
            return

        effective_lines = self._x_ar_get_effective_multi_lines()
        if not effective_lines:
            raise UserError(_("Debe agregar al menos una línea de pago."))

        if not any((line.amount or 0.0) > 0.0 for line in effective_lines):
            raise UserError(_("Debe indicar un importe mayor a cero en al menos una línea de pago."))

        check_lines = effective_lines.filtered(lambda l: self._is_latam_check_line(l))
        new_check_lines = check_lines.filtered(
            lambda l: l.payment_method_line_id.code in {"new_third_party_checks", "own_checks"}
        )
        move_check_lines = check_lines.filtered(
            lambda l: l.payment_method_line_id.code in {
                "in_third_party_checks", "out_third_party_checks", "return_third_party_checks"
            }
        )

        if len(new_check_lines) > 1:
            # Permitir múltiples líneas de cheques propios si son de diferentes bancos
            banks_used = {}
            for line in new_check_lines:
                journal_bank = line.journal_id.bank_account_id.bank_id if line.journal_id.bank_account_id else False
                if not journal_bank:
                    raise UserError(_(
                        "El diario '%s' no tiene cuenta bancaria con banco configurado.\n\n"
                        "Para usar múltiples líneas de cheques propios, configurá la cuenta bancaria en cada diario."
                    ) % line.journal_id.name)
                if journal_bank.id in banks_used:
                    raise UserError(_(
                        "Ya existe una línea de cheque propio para el banco '%s'.\n"
                        "Use una sola línea por banco."
                    ) % journal_bank.name)
                banks_used[journal_bank.id] = line
        
        if len(move_check_lines) > 1:
            raise UserError(_("Use una sola línea por tipo de cheque de terceros cuando utiliza múltiples métodos de pago."))

        # Validar que todos los cheques estén asignados a alguna línea
        if len(new_check_lines) > 1 and self.l10n_latam_new_check_ids:
            # Recopilar los bancos configurados en las líneas
            configured_bank_ids = set()
            for line in new_check_lines:
                journal_bank = line.journal_id.bank_account_id.bank_id if line.journal_id.bank_account_id else False
                if journal_bank:
                    configured_bank_ids.add(journal_bank.id)
            
            # Buscar cheques que no tienen banco o cuyo banco no coincide con ninguna línea
            orphan_checks = []
            for check in self.l10n_latam_new_check_ids:
                if not check.bank_id:
                    orphan_checks.append(_("Cheque '%s' no tiene banco asignado") % check.name)
                elif check.bank_id.id not in configured_bank_ids:
                    orphan_checks.append(_("Cheque '%s' (%s) - No hay diario configurado para este banco") % (
                        check.name, check.bank_id.name
                    ))
            
            if orphan_checks:
                raise UserError(_(
                    "Los siguientes cheques no se pueden asignar a ninguna línea de pago:\n\n"
                    "%s\n\n"
                    "Para solucionarlo:\n"
                    "• Configurá la cuenta bancaria con el banco correcto en cada diario, o\n"
                    "• Eliminá los cheques que no correspondan"
                ) % "\n".join("• " + msg for msg in orphan_checks))

    def _apply_latam_checks_to_payment_vals(self, payment_vals, line):
        """Aplica los cheques a los valores del pago, filtrando por banco del diario."""
        self.ensure_one()

        if not self._is_latam_check_line(line):
            return payment_vals

        code = line.payment_method_line_id.code
        if code in {"new_third_party_checks", "own_checks"}:
            if not self.l10n_latam_new_check_ids:
                raise UserError(_("Agregá los cheques en la pestaña Cheques para esta línea de pago."))
            
            # Contar cuántas líneas de cheques propios hay
            all_new_check_lines = self.payment_line_ids.filtered(
                lambda l: l.payment_method_line_id.code in {"new_third_party_checks", "own_checks"}
            )
            
            # Si hay una sola línea de cheques propios, asignar todos los cheques
            if len(all_new_check_lines) <= 1:
                checks_for_line = self.l10n_latam_new_check_ids
            else:
                # Si hay múltiples líneas, filtrar por banco del diario
                journal_bank = line.journal_id.bank_account_id.bank_id if line.journal_id.bank_account_id else False
                
                if not journal_bank:
                    raise UserError(_(
                        "El diario '%s' no tiene una cuenta bancaria con banco configurado.\n\n"
                        "Para usar múltiples líneas de cheques propios, cada diario debe tener "
                        "configurada su cuenta bancaria con el banco correspondiente."
                    ) % line.journal_id.name)
                
                # Filtrar cheques que coincidan con el banco del diario
                checks_for_line = self.l10n_latam_new_check_ids.filtered(
                    lambda c: c.bank_id.id == journal_bank.id if c.bank_id else False
                )
                
                if not checks_for_line:
                    available_banks = ", ".join(set(
                        c.bank_id.name for c in self.l10n_latam_new_check_ids if c.bank_id
                    )) or "Sin banco asignado"
                    raise UserError(_(
                        "No hay cheques del banco '%s' (requerido por el diario '%s').\n\n"
                        "Bancos de los cheques cargados: %s"
                    ) % (journal_bank.name, line.journal_id.name, available_banks))
            
            total_checks_amount = sum(checks_for_line.mapped("amount"))

            payment_vals["l10n_latam_new_check_ids"] = [Command.create({
                "name": x.name,
                "bank_id": x.bank_id.id if x.bank_id else False,
                "issuer_vat": x.issuer_vat,
                "payment_date": x.payment_date,
                "amount": x.amount,
            }) for x in checks_for_line]
            payment_vals["amount"] = total_checks_amount
        else:
            if not self.l10n_latam_move_check_ids:
                raise UserError(_("Seleccioná los cheques en la pestaña Cheques para esta línea de pago."))
            total_checks_amount = sum(self.l10n_latam_move_check_ids.mapped("amount"))

            payment_vals["l10n_latam_move_check_ids"] = [Command.link(x.id) for x in self.l10n_latam_move_check_ids]
            payment_vals["amount"] = total_checks_amount

        return payment_vals
    
    def _apply_latam_checks_to_single_payment_vals(self, payment_vals):
        """Aplica al pago simple la misma lógica de cheques del multi pago."""
        self.ensure_one()

        bucket = self._x_ar_get_check_bucket(self.payment_method_line_id)
        if not bucket:
            return payment_vals

        net_amount = self.x_ar_payment_instrument_amount

        if bucket == "new":
            if not self.l10n_latam_new_check_ids:
                raise UserError(_("Agregá los cheques en la pestaña Cheques antes de crear el pago."))

            total_checks_amount = sum(self.l10n_latam_new_check_ids.mapped("amount"))
            # No validamos monto: cheque mayor = anticipo, cheque menor = pago parcial

            payment_vals["l10n_latam_new_check_ids"] = [Command.create({
                "name": x.name,
                "bank_id": x.bank_id.id,
                "issuer_vat": x.issuer_vat,
                "payment_date": x.payment_date,
                "amount": x.amount,
            }) for x in self.l10n_latam_new_check_ids]
            # El pago se crea por el monto del cheque
            payment_vals["amount"] = total_checks_amount
            return payment_vals

        if bucket == "move":
            if not self.l10n_latam_move_check_ids:
                raise UserError(_("Seleccioná los cheques en la pestaña Cheques antes de crear el pago."))

            total_checks_amount = sum(self.l10n_latam_move_check_ids.mapped("amount"))
            # No validamos monto: cheque mayor = anticipo, cheque menor = pago parcial

            payment_vals["l10n_latam_move_check_ids"] = [Command.link(x.id) for x in self.l10n_latam_move_check_ids]
            # El pago se crea por el monto del cheque
            payment_vals["amount"] = total_checks_amount
            return payment_vals

        return payment_vals

    def _create_payment_vals_from_line_multi(self, lines_to_reconcile, line):
        """Crear valores del payment para una línea de múltiple pago.
        En V3 las líneas de método NO cargan la retención.
        """
        self.ensure_one()

        first_line = lines_to_reconcile[:1] or self.line_ids[:1]
        first_line = first_line[0] if first_line else False

        payment_vals = {
            "date": self.payment_date,
            "amount": line.amount,
            "payment_type": self.payment_type,
            "partner_type": self.partner_type,
            "memo": line.communication or self.communication,
            "journal_id": line.journal_id.id,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "partner_id": self.partner_id.id,
            "partner_bank_id": line.partner_bank_id.id or self.partner_bank_id.id,
            "payment_method_line_id": line.payment_method_line_id.id,
            "destination_account_id": first_line.account_id.id if first_line else self.line_ids[0].account_id.id,
            "write_off_line_vals": [],
        }

        payment_vals = self._apply_latam_checks_to_payment_vals(payment_vals, line)
        return payment_vals

    def _get_withholding_adjustment_journal(self):
        self.ensure_one()
        journal = self.env["account.journal"].search([
            ("company_id", "=", self.company_id.id),
            ("type", "=", "general"),
        ], limit=1)
        if not journal:
            raise UserError(_("No se encontró un diario general para registrar la retención separada."))
        return journal

    def _prepare_adjustment_line_from_writeoff(self, vals, partner_id):
        # Validar que tenga account_id
        if not vals.get("account_id"):
            tax_name = vals.get("name", _("Desconocido"))
            raise UserError(_(
                "La retención '%s' no tiene cuenta contable configurada para la empresa '%s'.\n\n"
                "Verificá que:\n"
                "• El impuesto de retención tenga una cuenta en 'Distribución de facturas'\n"
                "• La cuenta contable tenga la empresa '%s' en el campo 'Empresas'"
            ) % (tax_name, self.company_id.name, self.company_id.name))
        
        line_vals = {
            "name": vals.get("name") or _("Retención"),
            "account_id": vals["account_id"],
            "partner_id": vals.get("partner_id") or partner_id,
            "balance": vals.get("balance", 0.0),
        }

        if vals.get("currency_id"):
            line_vals["currency_id"] = vals["currency_id"]
            line_vals["amount_currency"] = vals.get("amount_currency", 0.0)

        if vals.get("tax_base_amount"):
            line_vals["tax_base_amount"] = vals["tax_base_amount"]
        if vals.get("tax_repartition_line_id"):
            line_vals["tax_repartition_line_id"] = vals["tax_repartition_line_id"]
        if vals.get("tax_ids"):
            line_vals["tax_ids"] = vals["tax_ids"]
        if vals.get("tax_tag_ids"):
            line_vals["tax_tag_ids"] = vals["tax_tag_ids"]
        if vals.get("analytic_distribution"):
            line_vals["analytic_distribution"] = vals["analytic_distribution"]

        return line_vals

    def _prepare_withholding_adjustment_move_vals(self, lines_to_reconcile):
        self.ensure_one()

        if not self.l10n_ar_withholding_ids:
            return False

        batch_result = {"lines": lines_to_reconcile}
        payment_vals = self._create_payment_vals_from_wizard(batch_result)
        write_off_line_vals = payment_vals.get("write_off_line_vals") or []

        if not write_off_line_vals:
            return False

        destination_account_id = payment_vals.get("destination_account_id")
        if not destination_account_id:
            first_line = lines_to_reconcile[:1] or self.line_ids[:1]
            first_line = first_line[0] if first_line else False
            destination_account_id = first_line.account_id.id if first_line else False

        if not destination_account_id:
            raise UserError(_("No se pudo determinar la cuenta por cobrar/pagar para la retención."))

        partner_id = payment_vals.get("partner_id") or self.partner_id.id
        total_balance = sum(x.get("balance", 0.0) for x in write_off_line_vals)
        total_amount_currency = sum(
            x.get("amount_currency", x.get("balance", 0.0)) for x in write_off_line_vals
        )

        line_ids = [
            Command.create({
                "name": _("Retención aplicada"),
                "account_id": destination_account_id,
                "partner_id": partner_id,
                "balance": -total_balance,
                **(
                    {
                        "currency_id": self.currency_id.id,
                        "amount_currency": -total_amount_currency,
                    }
                    if self.currency_id != self.company_id.currency_id
                    else {}
                ),
            })
        ]

        for vals in write_off_line_vals:
            line_ids.append(Command.create(
                self._prepare_adjustment_line_from_writeoff(vals, partner_id)
            ))

        return {
            "date": self.payment_date,
            "ref": self.communication or _("Retención %s") % (self.partner_id.display_name or ""),
            "journal_id": self._get_withholding_adjustment_journal().id,
            "company_id": self.company_id.id,
            "line_ids": line_ids,
        }

    def _create_withholding_adjustment_move(self, lines_to_reconcile):
        self.ensure_one()

        move_vals = self._prepare_withholding_adjustment_move_vals(lines_to_reconcile)
        if not move_vals:
            return self.env["account.move"]

        move = self.env["account.move"].create(move_vals)
        move.action_post()
        return move

    def _init_multi_payments(self, to_process):
        payments = self.env["account.payment"].with_context(skip_invoice_sync=True).create(
            [x["create_vals"] for x in to_process]
        )
        for payment, vals in zip(payments, to_process):
            vals["payment"] = payment
        return payments

    def _post_multi_payments(self, payments):
        if payments:
            self._x_ar_refresh_created_check_payment_amounts(payments)
            payments.action_post()
            self._x_ar_refresh_created_check_payment_amounts(payments)

    def _x_ar_reconcile_multi_payments(self, payments, adjustment_move, lines_to_reconcile):
        domain = [
            ("parent_state", "=", "posted"),
            ("account_type", "in", self.env["account.payment"]._get_valid_payment_account_types()),
            ("reconciled", "=", False),
        ]

        counterpart_lines = lines_to_reconcile.filtered_domain(domain)
        payment_lines = payments.move_id.line_ids.filtered_domain(domain) if payments else self.env["account.move.line"]
        adjustment_lines = adjustment_move.line_ids.filtered_domain(domain) if adjustment_move else self.env["account.move.line"]

        all_lines = counterpart_lines | payment_lines | adjustment_lines
        for account in all_lines.account_id:
            all_lines.filtered_domain([
                ("account_id", "=", account.id),
                ("reconciled", "=", False),
                ("parent_state", "=", "posted"),
            ]).reconcile()

        if payments:
            lines_to_reconcile.move_id.matched_payment_ids += payments

    def _x_ar_refresh_created_check_payment_amounts(self, payments):
        """Corrige el importe de pagos por cheque que quedaron en 0 tras el create."""
        check_codes = self._get_latam_check_codes()
        for payment in payments.filtered(
            lambda p: p.payment_method_line_id and p.payment_method_line_id.code in check_codes
        ):
            check_total = 0.0
            if hasattr(payment, "l10n_latam_new_check_ids") and payment.l10n_latam_new_check_ids:
                check_total += sum(payment.l10n_latam_new_check_ids.mapped("amount"))
            if hasattr(payment, "l10n_latam_move_check_ids") and payment.l10n_latam_move_check_ids:
                check_total += sum(payment.l10n_latam_move_check_ids.mapped("amount"))
            currency = payment.currency_id or payment.company_id.currency_id
            if check_total and currency and currency.compare_amounts(payment.amount, check_total) != 0 and payment.state == "draft":
                payment.write({"amount": check_total})

    def _x_ar_prepare_multi_receipt_payload(self, payments, lines_to_reconcile):
        """Construye el payload JSON del recibo resumido."""
        self.ensure_one()

        # Facturas involucradas
        valid_account_types = self.env["account.payment"]._get_valid_payment_account_types()
        target_lines = lines_to_reconcile.filtered(lambda l: l.account_type in valid_account_types)
        invoices = []
        for move in target_lines.mapped("move_id").sorted(key=lambda m: (m.invoice_date or m.date or fields.Date.today(), m.id)):
            move_lines = target_lines.filtered(lambda l, mv=move: l.move_id == mv)
            applied = sum(
                abs(l.amount_residual_currency) if (self.currency_id and l.currency_id == self.currency_id)
                else abs(l.amount_residual)
                for l in move_lines
            )
            invoices.append({
                "name": move.name or move.ref or move.display_name,
                "date": str(move.invoice_date or move.date or ""),
                "amount_total": abs(move.amount_total),
                "applied_amount": applied,
            })

        # Medios de pago
        payment_rows = []
        for payment in payments.sorted(key=lambda p: (p.date or fields.Date.today(), p.id)):
            payment_rows.append({
                "payment_name": payment.name or "/",
                "journal": payment.journal_id.display_name or "",
                "method": payment.payment_method_line_id.display_name or "",
                "amount": payment.amount,
            })

        # Cheques
        checks = []
        for check in self.l10n_latam_new_check_ids:
            checks.append({
                "type": _("Nuevo / propio"),
                "number": check.name or "",
                "bank": check.bank_id.name or "",
                "payment_date": str(check.payment_date or ""),
                "amount": check.amount,
            })
        for check in self.l10n_latam_move_check_ids:
            checks.append({
                "type": _("Tercero existente"),
                "number": check.name or "",
                "bank": check.bank_id.name or "",
                "payment_date": str(check.payment_date or ""),
                "amount": check.amount,
            })

        # Retenciones
        withholdings = []
        for wth in self._x_ar_get_active_withholdings():
            name = ""
            if "tax_id" in wth._fields and wth.tax_id:
                name = wth.tax_id.display_name or wth.tax_id.name
            amount = wth.x_manual_amount_value if wth.x_manual_amount_value else wth.amount
            withholdings.append({
                "name": name or _("Retención"),
                "base_amount": wth.base_amount if "base_amount" in wth._fields else 0.0,
                "amount": amount,
            })

        return {
            "partner_name": self.partner_id.display_name or "",
            "payment_date": str(self.payment_date or ""),
            "currency_name": self.currency_id.name or "",
            "document_total": self.x_ar_document_total_amount,
            "payment_total": sum(x["amount"] for x in payment_rows),
            "withholding_total": sum(x["amount"] for x in withholdings),
            "invoice_count": len(invoices),
            "payment_names": ", ".join(x["payment_name"] for x in payment_rows if x.get("payment_name")),
            "invoices": invoices,
            "payments": payment_rows,
            "checks": checks,
            "withholdings": withholdings,
        }

    def _create_payment_vals_from_single_custom(self, lines_to_reconcile):
        """Arma el payment simple con importe neto real del instrumento
        y sin write_offs en el payment, porque la retención irá en asiento separado.
        """
        self.ensure_one()

        first_line = lines_to_reconcile[:1] or self.line_ids[:1]
        first_line = first_line[0] if first_line else False

        payment_vals = {
            "date": self.payment_date,
            "amount": self.x_ar_payment_instrument_amount,
            "payment_type": self.payment_type,
            "partner_type": self.partner_type,
            "memo": self.communication,
            "journal_id": self.journal_id.id,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "partner_id": self.partner_id.id,
            "partner_bank_id": self.partner_bank_id.id,
            "payment_method_line_id": self.payment_method_line_id.id,
            "destination_account_id": first_line.account_id.id if first_line else self.line_ids[0].account_id.id,
            "write_off_line_vals": [],
        }

        payment_vals = self._apply_latam_checks_to_single_payment_vals(payment_vals)
        return payment_vals

    def _validate_withholding_accounts(self):
        """Valida que las retenciones tengan cuentas configuradas para la empresa actual."""
        self.ensure_one()
        
        for wth in self._x_ar_get_active_withholdings():
            if not hasattr(wth, 'tax_id') or not wth.tax_id:
                continue
            
            tax = wth.tax_id
            # Verificar que el impuesto tenga líneas de repartición con cuenta
            repartition_lines = tax.invoice_repartition_line_ids.filtered(
                lambda l: l.repartition_type == 'tax'
            )
            
            if not repartition_lines:
                raise UserError(_(
                    "El impuesto de retención '%s' no tiene líneas de distribución configuradas.\n\n"
                    "Verificá la configuración del impuesto en Contabilidad → Configuración → Impuestos."
                ) % tax.display_name)
            
            for line in repartition_lines:
                if not line.account_id:
                    raise UserError(_(
                        "El impuesto de retención '%s' no tiene cuenta contable en la línea de distribución.\n\n"
                        "Verificá que tenga una cuenta en 'Distribución de facturas' → línea 'de impuesto'."
                    ) % tax.display_name)
                
                # Verificar que la cuenta sea accesible para la empresa actual
                if line.account_id.company_ids and self.company_id not in line.account_id.company_ids:
                    raise UserError(_(
                        "La cuenta '%s' del impuesto '%s' no está habilitada para la empresa '%s'.\n\n"
                        "Agregá la empresa '%s' en el campo 'Empresas' de la cuenta contable,\n"
                        "o creá un impuesto de retención específico para esta empresa."
                    ) % (line.account_id.display_name, tax.display_name, 
                         self.company_id.name, self.company_id.name))

    def _create_single_payment_with_withholding(self):
        """Replica en pago normal la lógica del multi pago:
        - payment por el neto real
        - asiento separado de retención
        - conciliación conjunta
        """
        self.ensure_one()
        
        # Validar configuración de retenciones antes de procesar
        self._validate_withholding_accounts()

        for wth in self._x_ar_get_active_withholdings():
            if wth.x_manual_amount_value and self.currency_id.compare_amounts(
                wth.x_manual_amount_value, wth.amount
            ) != 0:
                wth.amount = wth.x_manual_amount_value

        # No validamos monto de cheques: permite pago parcial (cheque menor) o anticipo (cheque mayor)

        batches = self.batches
        if not batches:
            raise UserError(_("No se encontraron líneas para procesar el pago."))

        all_lines_to_reconcile = self.env["account.move.line"]
        for batch in batches:
            all_lines_to_reconcile |= batch["lines"]

        if not all_lines_to_reconcile:
            raise UserError(_("No se encontraron apuntes a reconciliar."))

        payment_vals = self._create_payment_vals_from_single_custom(all_lines_to_reconcile)

        to_process = [{
            "create_vals": payment_vals,
            "to_reconcile": all_lines_to_reconcile,
        }]

        payments = self._init_multi_payments(to_process)
        self._post_multi_payments(payments)

        adjustment_move = self._create_withholding_adjustment_move(all_lines_to_reconcile)

        if adjustment_move:
            payments.write({
                "x_ar_withholding_move_id": adjustment_move.id,
            })

        self._x_ar_reconcile_multi_payments(
            payments,
            adjustment_move,
            all_lines_to_reconcile,
        )

        payload = self._x_ar_prepare_multi_receipt_payload(payments, all_lines_to_reconcile)
        payload_json = json.dumps(payload, ensure_ascii=False)
        payments.write({
            "x_ar_multi_receipt_payload": payload_json,
        })

        return payments, adjustment_move

    def _create_multi_payments(self):
        self.ensure_one()

        self._x_ar_sync_multi_check_line_amounts()

        # Sincronizar valores manuales de retenciones antes de construir el pago
        for wth in self._x_ar_get_active_withholdings():
            if wth.x_manual_amount_value and self.currency_id.compare_amounts(
                wth.x_manual_amount_value, wth.amount
            ) != 0:
                wth.amount = wth.x_manual_amount_value

        self._validate_multi_payment()
        
        # Validar configuración de retenciones antes de procesar
        if self._x_ar_get_active_withholdings():
            self._validate_withholding_accounts()

        batches = self.batches
        if not batches:
            raise UserError(_("No se encontraron líneas para procesar el pago."))

        all_lines_to_reconcile = self.env["account.move.line"]
        for batch in batches:
            all_lines_to_reconcile |= batch["lines"]

        if not all_lines_to_reconcile:
            raise UserError(_("No se encontraron apuntes a reconciliar."))

        payment_lines = self._x_ar_get_effective_multi_lines().filtered(
            lambda l: (l.amount or 0.0) > 0.0
        )

        group_key = uuid4().hex
        to_process = []
        for line in payment_lines:
            payment_vals = self._create_payment_vals_from_line_multi(
                all_lines_to_reconcile,
                line,
            )
            payment_vals["x_ar_multi_payment_group_key"] = group_key
            to_process.append({
                "create_vals": payment_vals,
                "to_reconcile": all_lines_to_reconcile,
                "line": line,
            })

        payments = self._init_multi_payments(to_process)
        self._post_multi_payments(payments)

        adjustment_move = self._create_withholding_adjustment_move(all_lines_to_reconcile)

        # Vincular cada pago al asiento de retención (solo referencial)
        if adjustment_move:
            payments.write({"x_ar_withholding_move_id": adjustment_move.id})

        self._x_ar_reconcile_multi_payments(
            payments,
            adjustment_move,
            all_lines_to_reconcile,
        )

        # Guardar payload del recibo resumido en cada pago
        payload = self._x_ar_prepare_multi_receipt_payload(payments, all_lines_to_reconcile)
        payload_json = json.dumps(payload, ensure_ascii=False)
        payments.write({"x_ar_multi_receipt_payload": payload_json})

        return payments, adjustment_move

    def action_create_payments(self):
        for wizard in self:
            if wizard.use_multi_payment:
                payments, adjustment_move = wizard._create_multi_payments()
                action_domain = [("id", "in", payments.ids)]
                return {
                    "type": "ir.actions.act_window",
                    "name": _("Pagos"),
                    "res_model": "account.payment",
                    "view_mode": "list,form",
                    "domain": action_domain,
                }

            if wizard._x_ar_should_use_custom_single_payment():
                payments, adjustment_move = wizard._create_single_payment_with_withholding()
                action_domain = [("id", "in", payments.ids)]
                return {
                    "type": "ir.actions.act_window",
                    "name": _("Pagos"),
                    "res_model": "account.payment",
                    "view_mode": "list,form",
                    "domain": action_domain,
                }

            # No validamos monto de cheques: permite pago parcial o anticipo

            for wth in wizard.l10n_ar_withholding_ids:
                if wth.x_manual_amount_value and wizard.currency_id.compare_amounts(
                    wth.x_manual_amount_value, wth.amount
                ) != 0:
                    wth.amount = wth.x_manual_amount_value

        return super().action_create_payments()
