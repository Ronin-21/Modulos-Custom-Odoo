# -*- coding: utf-8 -*-
import logging

from odoo import _, Command, api, fields, models
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)


class PrsMoneyFlowCard(models.Model):
    _inherit = 'prs.money.flow'

    commission_move_id = fields.Many2one(
        'account.move',
        string='Asiento de comisión',
        readonly=True,
        copy=False,
        ondelete='set null',
    )
    commission_move_count = fields.Integer(
        string='Comisiones',
        compute='_compute_commission_move_count',
    )

    @api.depends('commission_move_id')
    def _compute_commission_move_count(self):
        for flow in self:
            flow.commission_move_count = 1 if flow.commission_move_id else 0

    def action_open_commission_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.commission_move_id.id,
        }

    def action_create_statement_line(self):
        """Override para liquidaciones de tarjeta: crea transferencia interna Clover → Banco."""
        card_flows = self.filtered(
            lambda f: (
                f.flow_type == 'card_settlement'
                and f.payment_id
                and not f.statement_line_id
                and f.state not in ('cancelled', 'rejected', 'statement_created', 'reconciled')
            )
        )
        other_flows = self - card_flows
        if other_flows:
            super(PrsMoneyFlowCard, other_flows).action_create_statement_line()
        for flow in card_flows:
            flow._prs_accredit_card_transfer()
        return True

    # =========================================================================
    # Acreditación por transferencia interna
    # =========================================================================

    def _prs_accredit_card_transfer(self):
        """Transfiere el bruto desde el diario puente (Tarjetas Clover) al diario
        destino (Banco Patagonia), acreditando el neto y registrando la comisión."""
        self.ensure_one()

        payment = self.payment_id
        src_journal = payment.journal_id    # Tarjetas Clover
        dst_journal = self.journal_id       # Banco Patagonia
        company = self.company_id

        transfer_account = self._prs_card_find_transfer_account(company)
        if not transfer_account:
            _logger.warning(
                'PRS Card: sin cuenta de transferencia para empresa "%s". '
                'Configurar "Transferencia de liquidez" en la compañía.',
                company.display_name,
            )
            super().action_create_statement_line()
            return

        date = self.actual_date or self.expected_date or fields.Date.context_today(self)
        label = self.label or self.name or _('Liquidación tarjeta')
        gross = self.amount_gross
        net = abs(self.amount_net)
        fee = (self.fee_amount or 0.0) + (self.fee_tax_amount or 0.0)
        rounding = self.currency_id.rounding

        # Partner del procesador: se usa en dst_line y comisión.
        # src_line conserva el partner del cliente (self.partner_id) para reconciliar con el PBNK.
        provider = src_journal.prs_card_provider_id
        provider_partner = provider.partner_id or None

        # 1. Extracto en diario puente (Tarjetas Clover): -bruto → dinero que sale
        src_line = self._prs_card_create_statement_line(src_journal, -gross, label, date)

        # 2. Reemplazar cuenta suspense por cuenta de transferencia en el asiento
        self._prs_card_validate_against_transfer(src_line, transfer_account)

        # 3. Reconciliar la cuenta del diario puente entre el pago original y el extracto
        self._prs_card_reconcile_src_with_payment(src_line, payment, src_journal)

        # 4. Extracto en diario destino (Banco Patagonia): +neto → dinero que entra
        dst_line = self._prs_card_create_statement_line(
            dst_journal, net, label, date, partner=provider_partner,
        )

        # 5. Reemplazar cuenta suspense en destino por cuenta de transferencia
        self._prs_card_validate_against_transfer(dst_line, transfer_account)

        # 6. Registrar comisión: primero cuenta del diario, luego cuenta global de la compañía
        commission_aml = None
        fee_account = (
            dst_journal.prs_flow_fee_account_id
            or company.prs_default_flow_fee_account_id
        )
        if not float_is_zero(fee, precision_rounding=rounding) and fee_account:
            commission_aml = self._prs_card_book_commission(
                fee_account, transfer_account, fee, label, date, company,
                partner=provider_partner,
            )

        # 7. Cerrar cuenta de transferencia: reconciliar DR (de Clover) con CR (de Banco y comisión)
        self._prs_card_reconcile_transfer_lines(
            src_line, dst_line, transfer_account, commission_aml,
        )

        # 8. Actualizar estado del flujo
        write_vals = {
            'statement_line_id': dst_line.id,
            'state': 'statement_created',
            'actual_date': date,
        }
        if commission_aml:
            write_vals['commission_move_id'] = commission_aml.move_id.id
        self.write(write_vals)

        _logger.info(
            'PRS Card: flujo %s acreditado vía transferencia interna '
            '(%s → %s | bruto=%.2f neto=%.2f comisión=%.2f).',
            self.id, src_journal.display_name, dst_journal.display_name,
            gross, net, fee,
        )

    # =========================================================================
    # Helpers contables
    # =========================================================================

    def _prs_card_find_transfer_account(self, company):
        """Devuelve la cuenta 'Transferencia de liquidez' para la compañía."""
        company = company.sudo()
        for field_name in (
            'transfer_account_id',
            'account_internal_transfer_account_id',
            'internal_transfer_account_id',
        ):
            if field_name in company._fields:
                acc = company[field_name]
                if acc and acc.exists():
                    return acc
        Account = self.env['account.account'].sudo().with_company(company)
        for search_name in ('Liquidity Transfer', 'Transferencia de liquidez', 'Transferencia'):
            acc = Account.search([('name', 'ilike', search_name)], limit=1)
            if acc:
                return acc
        return self.env['account.account']

    def _prs_card_create_statement_line(self, journal, amount, label, date, partner=None):
        """Crea un extracto bancario en el diario indicado.

        partner: si se pasa, sobreescribe self.partner_id como partner de la línea.
        Útil para que dst_line muestre el procesador en lugar del cliente.
        """
        company = journal.company_id
        vals = {
            'date': date,
            'payment_ref': label,
            'amount': amount,
            'journal_id': journal.id,
            'name': label,
            'company_id': company.id,
        }
        effective_partner = partner or self.partner_id
        if effective_partner:
            vals['partner_id'] = effective_partner.id
        return (
            self.env['account.bank.statement.line']
            .sudo()
            .with_company(company)
            .with_context(allowed_company_ids=[company.id])
            .create(vals)
        )

    def _prs_card_validate_against_transfer(self, statement_line, transfer_account):
        """Reemplaza la cuenta suspense del extracto por la cuenta de transferencia."""
        if not transfer_account.reconcile:
            try:
                transfer_account.write({'reconcile': True})
            except Exception:
                pass
        line = statement_line.sudo().with_company(statement_line.company_id)
        prepared = line._prepare_move_line_default_vals(counterpart_account_id=transfer_account.id)
        line.with_context(force_delete=True, skip_readonly_check=True).write({
            'line_ids': [Command.clear()] + [Command.create(v) for v in prepared],
            'checked': True,
        })
        if line.move_id:
            line.move_id.with_context(skip_readonly_check=True).write({'checked': True})

    def _prs_card_reconcile_src_with_payment(self, src_line, payment, src_journal):
        """Reconcilia la cuenta del diario puente entre el src_line y el PBNK del pago.

        El flujo correcto en Odoo 19 para pagos con tarjeta:
        - PBNK (move contable del pago): DR banco_puente / CR AR — reconcilia la factura
        - src_line (creado por la acreditación): CR banco_puente / DR cuenta_transferencia

        Reconciliamos PBNK DR ↔ src_line CR en la cuenta del diario puente para que
        el saldo de esa cuenta quede en cero.

        Si existe un extracto legacy del pago (BNK auto-creado erróneamente antes de
        que este fix estuviera desplegado), se intenta cancelar y eliminar. Si no es
        posible, se reconcilian sus líneas bancarias con src_line como fallback.
        """
        bank_account = src_journal.default_account_id
        if not bank_account:
            return
        if not bank_account.reconcile:
            try:
                bank_account.sudo().write({'reconcile': True})
            except Exception as exc:
                _logger.warning(
                    'PRS Card: no se pudo habilitar reconciliación en cuenta puente "%s": %s',
                    bank_account.display_name, exc,
                )
                return

        # Buscar extracto legacy del pago (solo existe si auto_create_statement=True antes del fix)
        LineModel = self.env['account.bank.statement.line']
        payment_stmt = self.env['account.bank.statement.line']
        if 'payment_id' in LineModel._fields:
            payment_stmt = LineModel.sudo().search([
                ('payment_id', '=', payment.id),
                ('journal_id', '=', src_journal.id),
            ], limit=1)

        if payment_stmt and payment_stmt.move_id:
            # Extracto legacy: intentar cancelar y eliminar para evitar doble DR en la cuenta puente
            cancelled = False
            try:
                if payment_stmt.move_id.state == 'posted':
                    payment_stmt.move_id.with_context(skip_readonly_check=True).button_cancel()
                payment_stmt.sudo().with_context(force_delete=True).unlink()
                cancelled = True
                _logger.info(
                    'PRS Card: extracto legacy del pago %s eliminado; procediendo con reconciliación normal.',
                    payment.display_name,
                )
            except Exception as exc:
                _logger.warning(
                    'PRS Card: no se pudo eliminar extracto legacy del pago %s: %s. '
                    'Reconciliando líneas bancarias como fallback.',
                    payment.display_name, exc,
                )

            if not cancelled:
                # Fallback: reconciliar banco_puente entre payment_stmt DR y src_line CR
                stmt_dr = payment_stmt.move_id.line_ids.filtered(
                    lambda l: l.account_id == bank_account and not l.reconciled
                )
                src_cr = src_line.move_id.line_ids.filtered(
                    lambda l: l.account_id == bank_account and not l.reconciled
                ) if src_line.move_id else self.env['account.move.line']
                if stmt_dr and src_cr:
                    try:
                        (stmt_dr + src_cr).sudo().reconcile()
                    except Exception as exc2:
                        _logger.warning(
                            'PRS Card: no se pudo reconciliar líneas legacy en "%s": %s',
                            bank_account.display_name, exc2,
                        )
                return

        # Camino normal: reconciliar PBNK DR(banco_puente) con src_line CR(banco_puente)
        payment_aml = payment.move_id.line_ids.filtered(
            lambda l: l.account_id == bank_account and not l.reconciled
        )
        src_aml = src_line.move_id.line_ids.filtered(
            lambda l: l.account_id == bank_account and not l.reconciled
        ) if src_line.move_id else self.env['account.move.line']
        if payment_aml and src_aml:
            try:
                (payment_aml + src_aml).sudo().reconcile()
            except Exception as exc:
                _logger.warning(
                    'PRS Card: no se pudo reconciliar PBNK con src_line en "%s": %s',
                    bank_account.display_name, exc,
                )

    def _prs_card_book_commission(
        self, fee_account, transfer_account, amount, label, date, company, partner=None,
    ):
        """Crea asiento de comisión: DR cuenta comisiones / CR cuenta transferencia.

        partner: procesador de tarjeta. Se asigna al encabezado del asiento y a la
        línea de gasto para identificar movimientos por procesador en reportes AP.
        """
        commission_label = _('Comisión: %s') % label
        move_vals = {
            'date': date,
            'journal_id': self.journal_id.id,
            'company_id': company.id,
            'ref': commission_label,
        }
        if partner:
            move_vals['partner_id'] = partner.id
        dr_line = {
            'account_id': fee_account.id,
            'name': commission_label,
            'debit': amount,
            'credit': 0.0,
        }
        if partner:
            dr_line['partner_id'] = partner.id
        move_vals['line_ids'] = [
            Command.create(dr_line),
            Command.create({
                'account_id': transfer_account.id,
                'name': commission_label,
                'debit': 0.0,
                'credit': amount,
            }),
        ]
        move = (
            self.env['account.move']
            .sudo()
            .with_company(company)
            .with_context(allowed_company_ids=[company.id])
            .create(move_vals)
        )
        move.action_post()
        return move.line_ids.filtered(lambda l: l.account_id == transfer_account)

    def _prs_card_reconcile_transfer_lines(self, src_line, dst_line, transfer_account, commission_aml=None):
        """Reconcilia todos los apuntes abiertos en la cuenta de transferencia."""
        def get_transfer_amls(stmt_line):
            if not stmt_line or not stmt_line.move_id:
                return self.env['account.move.line']
            return stmt_line.move_id.line_ids.filtered(
                lambda l: l.account_id == transfer_account and not l.reconciled
            )

        lines = get_transfer_amls(src_line) | get_transfer_amls(dst_line)
        if commission_aml:
            lines |= commission_aml.filtered(lambda l: not l.reconciled)

        if len(lines) >= 2:
            try:
                lines.sudo().reconcile()
            except Exception as exc:
                _logger.warning(
                    'PRS Card: no se pudo reconciliar cuenta de transferencia: %s', exc,
                )
