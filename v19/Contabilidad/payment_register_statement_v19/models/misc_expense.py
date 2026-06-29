# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)


class AccountReconcileModel(models.Model):
    """Extend reconciliation models to drive 'Gastos varios' accounting."""

    _inherit = 'account.reconcile.model'

    prs_use_for_misc_expense = fields.Boolean(
        string="Aplica a pagos 'Gasto vario'",
        help=(
            "Si está activo, este modelo se usará para determinar la cuenta contable "
            "a utilizar cuando un pago esté marcado como 'Gastos Varios'."
        ),
    )

    prs_misc_expense_account_id = fields.Many2one(
        'account.account',
        string="Cuenta de gasto",
        help=(
            "Cuenta contable que se usará como contrapartida del pago cuando esté "
            "marcado como 'Gastos Varios'."
        ),
    )

    prs_misc_payment_type = fields.Selection(
        selection=[
            ('outbound', 'Saliente'),
            ('inbound', 'Entrante'),
        ],
        string="Tipo de pago",
        default='outbound',
        required=True,
        help="Opcional: limite el modelo a pagos salientes/entrantes.",
    )

    prs_misc_journal_ids = fields.Many2many(
        'account.journal',
        'prs_reconcile_model_misc_journal_rel',
        'reconcile_model_id',
        'journal_id',
        string="Diarios",
        help="Opcional: si se completa, solo aplica a estos diarios.",
    )

    prs_misc_partner_ids = fields.Many2many(
        'res.partner',
        'prs_reconcile_model_misc_partner_rel',
        'reconcile_model_id',
        'partner_id',
        string="Proveedores/Clientes",
        help="Opcional: si se completa, solo aplica a estos contactos.",
    )

    prs_misc_memo_contains = fields.Char(
        string="Memo contiene",
        help="Opcional: texto que debe estar contenido en el memo/etiqueta del pago.",
    )


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    prs_is_misc_expense = fields.Boolean(string="Gastos Varios")

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    def _prs_account_is_receivable_or_payable(self, account):
        """Detect receivable/payable accounts across Odoo variants."""
        if not account:
            return False

        # Newer versions: account_type = 'asset_receivable' / 'liability_payable'
        if 'account_type' in account._fields:
            return account.account_type in (
                'asset_receivable',
                'liability_payable',
                'receivable',
                'payable',
            )

        # Older versions: internal_type = 'receivable' / 'payable'
        if 'internal_type' in account._fields:
            return account.internal_type in ('receivable', 'payable')

        # Very old: user_type_id.type
        if 'user_type_id' in account._fields and account.user_type_id and 'type' in account.user_type_id._fields:
            return account.user_type_id.type in ('receivable', 'payable')

        return False

    def _prs_get_misc_expense_account(self):
        """Resolve the expense account from reconciliation models configuration."""
        self.ensure_one()

        dom = [('prs_use_for_misc_expense', '=', True)]
        if 'company_id' in self.env['account.reconcile.model']._fields:
            dom += ['|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)]

        models_rs = self.env['account.reconcile.model'].search(dom, order='sequence, id')

        memo = (self.memo or getattr(self, 'communication', False) or self.name or '')
        memo_l = memo.lower() if memo else ''

        for rm in models_rs:
            # Type filter
            if rm.prs_misc_payment_type and rm.prs_misc_payment_type != self.payment_type:
                continue

            # Journal filter
            if rm.prs_misc_journal_ids and self.journal_id not in rm.prs_misc_journal_ids:
                continue

            # Partner filter
            if rm.prs_misc_partner_ids and self.partner_id not in rm.prs_misc_partner_ids:
                continue

            # Memo filter
            if rm.prs_misc_memo_contains:
                if rm.prs_misc_memo_contains.lower() not in memo_l:
                    continue

            if rm.prs_misc_expense_account_id:
                return rm.prs_misc_expense_account_id

        return False

    # ---------------------------------------------------------------------
    # Posting logic
    # ---------------------------------------------------------------------

    def _prepare_move_line_default_vals(self, *args, **kwargs):
        """If 'Gasto Vario' is enabled, force accounts (bank vs expense).

        Signature differences between Odoo versions are handled via *args/**kwargs.
        """
        self.ensure_one()
        line_vals = super()._prepare_move_line_default_vals(*args, **kwargs)

        if not self.prs_is_misc_expense:
            return line_vals

        # Only makes sense for bank/cash journals
        if self.journal_id.type not in ('bank', 'cash'):
            raise ValidationError(_("'Gastos Varios' solo aplica a diarios de Banco/Caja."))

        # Avoid mixing with invoice/bill payments (we are bypassing A/R & A/P)
        for fn in ('reconciled_invoice_ids', 'invoice_ids', 'reconciled_bill_ids', 'bill_ids'):
            if fn in self._fields and getattr(self, fn):
                raise ValidationError(
                    _("No se puede usar 'Gastos Varios' en pagos vinculados a facturas / documentos. "
                      "Use el pago normal para conciliar contra CxP/CxC.")
                )

        expense_account = self._prs_get_misc_expense_account()
        if not expense_account:
            raise ValidationError(
                _("No se encontró una 'Cuenta de gasto' para este pago.\n\n"
                  "Configure un Modelo de conciliación con 'Aplica a pagos Gasto vario' y una 'Cuenta de gasto'.")
            )

        if self._prs_account_is_receivable_or_payable(expense_account):
            raise ValidationError(
                _("La cuenta seleccionada para 'Gasto vario' no puede ser Por Cobrar / Por Pagar.")
            )

        bank_account = self.journal_id.default_account_id
        if not bank_account:
            raise ValidationError(
                _("El diario '%s' no tiene 'Cuenta por defecto' configurada.") % self.journal_id.display_name
            )

        def _abs_amount(vals):
            return abs((vals.get('debit') or 0.0) - (vals.get('credit') or 0.0))

        # Identify main lines
        if self.payment_type == 'outbound':
            liquidity_candidates = [l for l in line_vals if (l.get('credit') or 0.0) > 0.0]
            counterpart_candidates = [l for l in line_vals if (l.get('debit') or 0.0) > 0.0]
        else:
            liquidity_candidates = [l for l in line_vals if (l.get('debit') or 0.0) > 0.0]
            counterpart_candidates = [l for l in line_vals if (l.get('credit') or 0.0) > 0.0]

        liquidity_line = max(liquidity_candidates, key=_abs_amount, default=False)
        counterpart_line = max(
            [l for l in counterpart_candidates if l is not liquidity_line],
            key=_abs_amount,
            default=False,
        )

        if not liquidity_line or not counterpart_line:
            _logger.warning(
                "[PRS] No se pudieron identificar líneas principales para 'Gasto Vario' en payment %s", self.id
            )
            return line_vals

        # Force: bank account (ignores outstanding account) vs expense account
        liquidity_line['account_id'] = bank_account.id
        # Liquidity line should not create A/R A/P implication via partner
        liquidity_line['partner_id'] = False

        counterpart_line['account_id'] = expense_account.id
        counterpart_line['partner_id'] = self.partner_id.id or False

        # Safety: ensure we are not leaving a receivable/payable main line behind
        if self._prs_account_is_receivable_or_payable(self.env['account.account'].browse(counterpart_line['account_id'])):
            raise ValidationError(_("No se pudo forzar una cuenta válida para 'Gasto Vario'."))

        return line_vals
