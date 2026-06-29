# -*- coding: utf-8 -*-
import logging

from odoo import api, Command, fields, models, _
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class PosCashTransferPrs(models.Model):
    _inherit = 'pos.cash.transfer'

    prs_pending_validation = fields.Boolean(
        string="Pendiente de validación",
        compute='_compute_prs_pending_validation',
        store=True,
    )

    @api.depends(
        'state',
        'statement_line_to_id',
        'destination_journal_id',
        'destination_journal_id.prs_pos_deposit_require_validation',
    )
    def _compute_prs_pending_validation(self):
        for rec in self:
            rec.prs_pending_validation = (
                rec.state == 'posted'
                and not rec.statement_line_to_id
                and bool(getattr(rec.destination_journal_id, 'prs_pos_deposit_require_validation', False))
            )

    def action_confirm_reception(self):
        """Confirma la recepción en Caja Central.

        Flujo requerido:
        1) Validar primero la salida de la Caja POS contra Transferencia de liquidez.
        2) Crear luego la entrada en Caja Central.
        3) Validar esa entrada contra Transferencia de liquidez.
        4) Si ambas cajas pertenecen a la misma compañía, reconciliar las dos líneas
           de Transferencia de liquidez para dejar el puente cerrado.

        Importante: no se usa el fallback de conciliación directa contra la cuenta
        outstanding del diario, porque eso genera la contraparte incorrecta
        (por ejemplo "Créditos por ventas") en el widget de conciliación.
        """
        for rec in self:
            if not rec.prs_pending_validation:
                raise UserError(_(
                    "El depósito '%s' no está pendiente de validación."
                ) % rec.name)

            if not rec.statement_line_from_id:
                raise UserError(_(
                    "El depósito '%s' no tiene extracto de salida en la caja POS."
                ) % rec.name)

            src_journal = rec.journal_id
            dst_journal = rec.destination_journal_id
            src_company = src_journal.company_id
            dst_company = dst_journal.company_id
            amount = abs(rec.amount)
            user_name = self.env.user.name or "Administrador"
            cup = (rec.coupon_number or rec.name or '').strip()

            src_label = rec.statement_line_from_id.payment_ref or rec.statement_line_from_id.name or _(
                "Depósito realizado por %(user)s - N° %(cup)s"
            ) % {'user': user_name, 'cup': cup}
            dst_label = _("Depósito recibido por %(user)s - N° %(cup)s") % {
                'user': user_name,
                'cup': cup,
            }

            # 1) Buscar las cuentas de transferencia antes de tocar nada.
            src_transfer_account = self._prs_find_transfer_account(src_company)
            dst_transfer_account = self._prs_find_transfer_account(dst_company)
            if not src_transfer_account or not dst_transfer_account:
                raise UserError(_(
                    "No se encontró la cuenta 'Transferencia de liquidez' para la compañía origen o destino.\n\n"
                    "Configure la cuenta de transferencia interna en la compañía, o cree una cuenta con nombre "
                    "similar a 'Transferencia de liquidez' / 'Transferencia'."
                ))

            _logger.info(
                "PRS POS: confirmando depósito %s | origen=%s | destino=%s | importe=%s | cuenta origen=%s | cuenta destino=%s",
                rec.name,
                src_journal.display_name,
                dst_journal.display_name,
                amount,
                src_transfer_account.display_name,
                dst_transfer_account.display_name,
            )

            # 2) PRIMERO: validar la salida de Caja POS contra Transferencia de liquidez.
            self._prs_validate_statement_line_against_transfer(
                rec.statement_line_from_id,
                src_transfer_account,
                src_label,
            )

            # 3) DESPUÉS: crear la entrada en Caja Central.
            line_to = self._prs_create_destination_statement_line(
                rec,
                dst_journal,
                dst_company,
                amount,
                dst_label,
            )
            rec.sudo().write({'statement_line_to_id': line_to.id})

            # 4) Validar la entrada de Caja Central contra Transferencia de liquidez.
            self._prs_validate_statement_line_against_transfer(
                line_to,
                dst_transfer_account,
                dst_label,
            )

            # 5) Cerrar el puente si es la misma compañía.
            self._prs_reconcile_transfer_account_lines(
                rec.statement_line_from_id,
                line_to,
                src_transfer_account,
                dst_transfer_account,
            )

            rec.message_post(
                body=_(
                    "✅ Recepción confirmada por %(user)s. "
                    "Salida POS validada contra Transferencia de liquidez y entrada creada/validada en %(journal)s."
                ) % {'user': user_name, 'journal': dst_journal.display_name},
                subtype_xmlid='mail.mt_note',
            )

        return True

    # =========================================================================
    # Operaciones contables
    # =========================================================================

    def _prs_create_destination_statement_line(self, transfer, journal, company, amount, label):
        """Crea el extracto positivo en la caja destino."""
        vals = {
            'date': fields.Date.context_today(self),
            'payment_ref': label,
            'amount': amount,
            'journal_id': journal.id,
            'name': label,
            'company_id': company.id,
        }
        if transfer.partner_id:
            vals['partner_id'] = transfer.partner_id.id

        line = (
            self.env['account.bank.statement.line']
            .sudo()
            .with_company(company)
            .with_context(allowed_company_ids=[company.id])
            .create(vals)
        )
        _logger.info(
            "PRS POS: extracto destino %s creado en '%s'.",
            line.id,
            journal.display_name,
        )
        return line

    def _prs_validate_statement_line_against_transfer(self, statement_line, transfer_account, label):
        """Reemplaza la cuenta suspense/outstanding por Transferencia de liquidez.

        Es el mismo criterio usado por el wizard de Transferencia interna de
        payment_register_statement: se reconstruyen las líneas del asiento de la
        línea de extracto con `_prepare_move_line_default_vals` usando
        `counterpart_account_id`.
        """
        if not statement_line or not statement_line.exists():
            raise UserError(_("No se encontró la línea de extracto a validar."))
        if not transfer_account or not transfer_account.exists():
            raise UserError(_("No se encontró la cuenta de Transferencia de liquidez."))

        line = statement_line.sudo().with_company(statement_line.company_id)
        account = transfer_account.sudo().with_company(statement_line.company_id)

        if not account.reconcile:
            try:
                account.write({'reconcile': True})
            except Exception:
                _logger.warning(
                    "PRS POS: no se pudo activar reconcile=True en la cuenta '%s'.",
                    account.display_name,
                    exc_info=True,
                )

        try:
            prepared_lines = line._prepare_move_line_default_vals(
                counterpart_account_id=account.id
            )
            line.with_context(
                force_delete=True,
                skip_readonly_check=True,
            ).write({
                'line_ids': [Command.clear()] + [
                    Command.create(vals) for vals in prepared_lines
                ],
                'checked': True,
            })

            if line.move_id:
                line.move_id.with_context(
                    skip_readonly_check=True,
                ).write({'checked': True})

            _logger.info(
                "PRS POS: statement line %s validada contra '%s'.",
                line.id,
                account.display_name,
            )
        except Exception as e:
            _logger.exception(
                "PRS POS: error al validar statement line %s contra Transferencia de liquidez.",
                line.id,
            )
            raise UserError(_(
                "No se pudo validar el extracto '%(line)s' contra Transferencia de liquidez: %(error)s"
            ) % {'line': line.display_name, 'error': str(e)}) from e

    def _prs_reconcile_transfer_account_lines(self, line_from, line_to, src_transfer_account, dst_transfer_account):
        """Reconcilia los apuntes de transferencia si pertenecen a la misma compañía."""
        if not line_from or not line_to:
            return
        if line_from.company_id != line_to.company_id:
            _logger.info(
                "PRS POS: transferencia cross-company (%s → %s). No se reconcilia el puente entre compañías.",
                line_from.company_id.display_name,
                line_to.company_id.display_name,
            )
            return
        if src_transfer_account != dst_transfer_account:
            _logger.info(
                "PRS POS: cuentas de transferencia distintas (%s / %s). No se reconcilia automáticamente.",
                src_transfer_account.display_name,
                dst_transfer_account.display_name,
            )
            return

        transfer_account = src_transfer_account
        aml_from = line_from.move_id.line_ids.filtered(
            lambda l: l.account_id == transfer_account and not l.reconciled
        )
        aml_to = line_to.move_id.line_ids.filtered(
            lambda l: l.account_id == transfer_account and not l.reconciled
        )
        if not aml_from or not aml_to:
            _logger.warning(
                "PRS POS: no se encontraron apuntes abiertos de Transferencia de liquidez para reconciliar (from=%s, to=%s).",
                line_from.id,
                line_to.id,
            )
            return
        try:
            (aml_from + aml_to).sudo().reconcile()
            _logger.info(
                "PRS POS: apuntes de Transferencia de liquidez reconciliados para from=%s / to=%s.",
                line_from.id,
                line_to.id,
            )
        except Exception:
            _logger.warning(
                "PRS POS: no se pudo reconciliar automáticamente la cuenta de Transferencia de liquidez.",
                exc_info=True,
            )


    # =========================================================================
    # Anulación robusta PRS
    # =========================================================================

    @api.depends(
        'state',
        'pos_session_id',
        'pos_session_id.state',
        'statement_line_from_id',
        'statement_line_to_id',
        'destination_journal_id',
        'destination_journal_id.prs_pos_deposit_require_validation',
    )
    def _compute_is_cancellable(self):
        """Permite anular depósitos PRS aunque la sesión ya no sea la última."""
        super()._compute_is_cancellable()
        for rec in self:
            if (
                rec.state == 'posted'
                and rec.pos_session_id
                and rec.pos_session_id.state == 'closed'
                and bool(getattr(rec.destination_journal_id, 'prs_pos_deposit_require_validation', False))
            ):
                rec.is_cancellable = True

    def _ensure_can_cancel(self):
        """Validaciones propias para anular depósitos PRS.

        No se exige que la sesión sea la última cerrada, porque el objetivo de
        la anulación PRS es borrar el extracto de salida creado en la caja POS
        cuando el depósito aún no debe impactar o quedó mal generado.
        """
        self.ensure_one()

        if self.state != 'posted':
            raise UserError(_("El depósito ya está anulado."))

        if not self.env.user.has_group('pos_cash_transfer.group_pos_cash_transfer'):
            raise AccessError(_("No tiene permisos para anular depósitos POS."))

        if not self.pos_session_id or self.pos_session_id.state != 'closed':
            raise UserError(_("Solo se puede anular un depósito cuya sesión POS esté cerrada."))

    def action_cancel(self):
        """Anula el depósito eliminando sus extractos, no creando contrapartidas.

        Flujo buscado:
        - borrar el extracto negativo de la Caja POS;
        - si ya existía, borrar también el extracto positivo de Caja Central;
        - romper conciliaciones contra Transferencia de liquidez o cuentas
          transitorias generadas por versiones anteriores;
        - limpiar asientos puente auxiliares relacionados al mismo cupón.
        """
        for rec in self:
            rec._ensure_can_cancel()
            rec._prs_cancel_statement_deposit()
        return True

    def _prs_cancel_statement_deposit(self):
        self.ensure_one()

        amount = abs(self.amount or 0.0)
        coupon = (self.coupon_number or self.name or '').strip()
        amount_str = self._format_amount() if hasattr(self, '_format_amount') else str(amount)

        statement_lines = self._prs_collect_statement_lines_to_cancel()
        protected_move_ids = statement_lines.mapped('move_id').ids
        bridge_moves = self._prs_find_related_bridge_moves(coupon, amount, protected_move_ids)

        # 1) Borrar primero extractos. Esto borra sus asientos asociados.
        for line in statement_lines:
            self._prs_unlink_statement_line_force(line)

        # 2) Borrar asientos auxiliares/puente que pudieran haber quedado de
        #    versiones viejas con Cuenta transitoria / Transferencia de liquidez.
        for move in bridge_moves.exists():
            self._prs_unlink_move_force(move)

        # 3) Compatibilidad con campos históricos del módulo base.
        self._prs_unlink_move_force(self.move_from_id)
        self._prs_unlink_move_force(self.move_to_id)

        self.sudo().write({
            'state': 'cancelled',
            'cancelled_uid': self.env.user.id,
            'cancelled_date': fields.Datetime.now(),
            'statement_line_from_id': False,
            'statement_line_to_id': False,
            'move_from_id': False,
            'move_to_id': False,
        })

        msg = _("❌ Depósito anulado - Cupón: %s - Importe: %s. Se eliminaron los extractos asociados.") % (coupon or '-', amount_str)
        if self.pos_session_id:
            self.pos_session_id.message_post(body=msg, subtype_xmlid='mail.mt_note')
        self.message_post(body=msg, subtype_xmlid='mail.mt_note')


    def action_prs_cleanup_cancelled_residuals(self):
        """Limpia extractos/asientos que hayan quedado de una anulación vieja.

        Sirve para casos donde una versión anterior marcó el depósito como
        anulado, pero dejó en la Caja POS el extracto contra Cuenta transitoria
        o Transferencia de liquidez. Solo borra candidatos vinculados o un único
        candidato encontrado por cupón/importe.
        """
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError(_("Esta limpieza solo aplica a depósitos ya anulados."))

            amount = abs(rec.amount or 0.0)
            coupon = (rec.coupon_number or rec.name or '').strip()
            statement_lines = rec._prs_collect_statement_lines_to_cancel()
            protected_move_ids = statement_lines.mapped('move_id').ids
            bridge_moves = rec._prs_find_related_bridge_moves(coupon, amount, protected_move_ids)

            if not statement_lines and not bridge_moves:
                raise UserError(_(
                    "No se encontraron restos únicos para limpiar. Si el extracto sigue visible, elimínelo manualmente o revise que el cupón/importe del depósito coincidan."
                ))

            for line in statement_lines:
                rec._prs_unlink_statement_line_force(line)
            for move in bridge_moves.exists():
                rec._prs_unlink_move_force(move)

            rec.sudo().write({
                'statement_line_from_id': False,
                'statement_line_to_id': False,
                'move_from_id': False,
                'move_to_id': False,
            })
            rec.message_post(
                body=_("🧹 Restos contables/extractos de depósito anulado limpiados."),
                subtype_xmlid='mail.mt_note',
            )
        return True

    def _prs_collect_statement_lines_to_cancel(self):
        """Devuelve los extractos vinculados y, si faltan vínculos, busca por cupón.

        La búsqueda por cupón solo se usa como respaldo para depósitos creados
        por versiones anteriores que no hayan guardado correctamente el many2one.
        Si hay más de un candidato no se borra por búsqueda para evitar borrar
        un movimiento equivocado.
        """
        self.ensure_one()
        StatementLine = self.env['account.bank.statement.line'].sudo()
        lines = StatementLine

        for line in (self.statement_line_from_id, self.statement_line_to_id):
            if line and line.sudo().exists():
                lines |= line.sudo()

        coupon = (self.coupon_number or '').strip()
        if not coupon:
            return lines

        def fallback_line(journal, amount):
            if not journal:
                return StatementLine
            domain = [
                ('journal_id', '=', journal.id),
                ('amount', '=', amount),
                '|',
                    ('payment_ref', 'ilike', coupon),
                    ('name', 'ilike', coupon),
            ]
            candidates = StatementLine.search(domain)
            if len(candidates) == 1:
                return candidates
            if len(candidates) > 1:
                _logger.warning(
                    "PRS POS: no se borra por búsqueda fallback; hay %s extractos candidatos para cupón %s en diario %s.",
                    len(candidates), coupon, journal.display_name,
                )
            return StatementLine

        if not self.statement_line_from_id or not self.statement_line_from_id.sudo().exists():
            lines |= fallback_line(self.journal_id, -abs(self.amount))
        if self.statement_line_to_id and not self.statement_line_to_id.sudo().exists():
            lines |= fallback_line(self.destination_journal_id, abs(self.amount))

        return lines.exists()

    def _prs_ctx_company(self, company):
        return {
            'allowed_company_ids': [company.id],
            'skip_company_validation': True,
            'skip_readonly_check': True,
            'force_delete': True,
        }

    def _prs_remove_reconcile_force(self, lines):
        lines = lines.sudo().exists()
        if not lines:
            return
        try:
            lines.remove_move_reconcile()
        except Exception:
            _logger.warning(
                "PRS POS: no se pudo romper una conciliación antes de anular.",
                exc_info=True,
            )

    def _prs_unlink_statement_line_force(self, line):
        line = line.sudo().exists()
        if not line:
            return

        company = line.company_id
        line = line.with_company(company).with_context(**self._prs_ctx_company(company))
        move = line.move_id.sudo().exists() if line.move_id else self.env['account.move']

        if move:
            self._prs_unlink_move_force(move)

        # Releer luego de borrar el asiento: algunas versiones borran la línea
        # por cascada/lógica interna.
        line = self.env['account.bank.statement.line'].sudo().browse(line.id).exists()
        if not line:
            return

        line = line.with_company(line.company_id).with_context(**self._prs_ctx_company(line.company_id))
        vals = {}
        if 'checked' in line._fields:
            vals['checked'] = False
        if vals:
            try:
                line.write(vals)
            except Exception:
                pass
        try:
            line.unlink()
        except Exception as e:
            raise UserError(_(
                "No se pudo eliminar el extracto '%(line)s'. Revise si pertenece a un período bloqueado o si fue conciliado manualmente.\n\nDetalle: %(error)s"
            ) % {'line': line.display_name or line.name or line.id, 'error': str(e)}) from e

    def _prs_unlink_move_force(self, move):
        move = move.sudo().exists()
        if not move:
            return
        move = move.with_company(move.company_id).with_context(**self._prs_ctx_company(move.company_id))

        self._prs_remove_reconcile_force(move.line_ids)

        if move.state == 'posted':
            drafted = False
            for method_name in ('button_draft', 'button_cancel'):
                if hasattr(move, method_name):
                    try:
                        getattr(move, method_name)()
                        drafted = True
                        break
                    except Exception:
                        _logger.info(
                            "PRS POS: %s falló para asiento %s durante anulación.",
                            method_name, move.display_name,
                            exc_info=True,
                        )
            if not drafted and move.state == 'posted':
                raise UserError(_(
                    "No se pudo pasar a borrador/cancelar el asiento '%s'. Revise fechas bloqueadas o permisos contables."
                ) % move.display_name)

        move = move.sudo().exists()
        if not move:
            return
        move = move.with_company(move.company_id).with_context(**self._prs_ctx_company(move.company_id))
        if move.state != 'draft':
            try:
                move.button_draft()
            except Exception:
                pass
        if move.state != 'draft':
            raise UserError(_("No se pudo poner en borrador el asiento '%s' para eliminarlo.") % move.display_name)
        try:
            move.unlink()
        except Exception as e:
            raise UserError(_(
                "No se pudo eliminar el asiento '%(move)s'.\n\nDetalle: %(error)s"
            ) % {'move': move.display_name, 'error': str(e)}) from e

    def _prs_find_related_bridge_moves(self, coupon, amount, exclude_move_ids=None):
        """Busca asientos puente viejos ligados al cupón para limpiarlos.

        No toca asientos POS normales: solo candidatos tipo `entry` con el cupón
        en referencia/nombre y con cuentas de transferencia/transitorias o una
        línea por el mismo importe.
        """
        exclude_move_ids = exclude_move_ids or []
        Move = self.env['account.move'].sudo()
        if not coupon:
            return Move

        company_ids = list(set((self.journal_id.company_id | self.destination_journal_id.company_id).ids))
        domain = [
            ('move_type', '=', 'entry'),
            ('company_id', 'in', company_ids),
            ('id', 'not in', exclude_move_ids or [0]),
            '|',
                ('ref', 'ilike', coupon),
                ('line_ids.name', 'ilike', coupon),
        ]
        candidates = Move.search(domain)

        def is_bridge(move):
            # Debe tener alguna línea con el importe del depósito.
            has_amount = any(
                abs((line.debit or 0.0) - amount) < 0.01 or abs((line.credit or 0.0) - amount) < 0.01
                for line in move.line_ids
            )
            if not has_amount:
                return False

            account_text = ' '.join(move.line_ids.mapped('account_id.display_name')).lower()
            ref_text = ((move.ref or '') + ' ' + ' '.join(move.line_ids.mapped('name'))).lower()
            return (
                'transferencia' in account_text
                or 'liquidity' in account_text
                or 'transitoria' in account_text
                or 'transitorio' in account_text
                or 'depósito' in ref_text
                or 'deposito' in ref_text
            )

        related = candidates.filtered(is_bridge)
        if related:
            _logger.info(
                "PRS POS: asientos puente relacionados al cupón %s para borrar: %s",
                coupon, related.ids,
            )
        return related

    # =========================================================================
    # Helpers
    # =========================================================================

    def _prs_account_company_domain(self, company):
        Account = self.env['account.account']
        if 'company_ids' in Account._fields:
            return [('company_ids', 'in', company.id)]
        if 'company_id' in Account._fields:
            return [('company_id', '=', company.id)]
        return []

    def _prs_find_transfer_account(self, company):
        """Busca la cuenta de Transferencia de liquidez para la compañía."""
        company = company.sudo()
        candidate_fields = [
            'transfer_account_id',
            'internal_transfer_account_id',
            'account_internal_transfer_account_id',
            'account_journal_transfer_account_id',
            'liquidity_transfer_account_id',
            'account_journal_payment_debit_account_id',
        ]
        for field_name in candidate_fields:
            if field_name in company._fields:
                account = company[field_name]
                if account and account.exists():
                    _logger.info(
                        "PRS POS: cuenta de transferencia via company.%s: '%s'.",
                        field_name,
                        account.display_name,
                    )
                    return account

        Account = self.env['account.account'].sudo().with_company(company)
        company_domain = self._prs_account_company_domain(company)

        search_domains = [
            company_domain + [('name', 'ilike', 'Transferencia de liquidez')],
            company_domain + [('name', 'ilike', 'Transferencia')],
            company_domain + [('name', 'ilike', 'Liquidity Transfer')],
            company_domain + [('code', '=', '6.0.00.00.01')],
        ]
        for domain in search_domains:
            account = Account.search(domain, limit=1)
            if account:
                _logger.info(
                    "PRS POS: cuenta de transferencia encontrada por dominio %s: '%s'.",
                    domain,
                    account.display_name,
                )
                return account

        _logger.warning(
            "PRS POS: no se encontró cuenta de Transferencia de liquidez para '%s'.",
            company.display_name,
        )
        return self.env['account.account']
