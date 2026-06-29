# -*- coding: utf-8 -*-
import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class PosCashTransferWizardPrs(models.TransientModel):
    _inherit = 'pos.cash.transfer.wizard'

    def _create_cash_transfer_journal_entry(self):
        """Override: modo validación manual cuando el diario destino tiene
        prs_pos_deposit_require_validation = True.

        Crea SOLO la statement line negativa en Caja POS, sin reconciliar,
        para que quede "Por revisar" hasta que el admin confirme.

        Si el flag no está activo → comportamiento original sin cambios.
        """
        self.ensure_one()

        dst_journal = self.destination_journal_id

        # Diagnóstico explícito en el log para verificar si el flag está activo
        flag_value = getattr(dst_journal, 'prs_pos_deposit_require_validation', 'CAMPO NO EXISTE')
        _logger.info(
            "PRS POS wizard: diario destino='%s' (id=%s) | "
            "prs_pos_deposit_require_validation=%s",
            dst_journal.name, dst_journal.id, flag_value,
        )

        if not flag_value:
            _logger.info(
                "PRS POS wizard: flag desactivado o ausente → "
                "usando flujo original del módulo base."
            )
            return super()._create_cash_transfer_journal_entry()

        # ── Modo validación manual ───────────────────────────────────────────
        _logger.info(
            "PRS POS wizard: ✅ flag activo → "
            "creando SOLO extracto negativo en '%s' sin auto-reconciliar.",
            self.journal_id.name,
        )

        from_company = self.journal_id.company_id
        user_name    = self.env.user.name or "Usuario"
        cup          = (self.coupon_number or '').strip()
        texto        = "Depósito realizado por %s - N° %s" % (user_name, cup)

        # Creamos la statement line con un contexto que bloquea todos los
        # mecanismos de auto-reconciliación que Odoo podría disparar:
        # - skip_account_move_synchronization: no sincroniza moves automáticamente
        # - no_recompute: evita recomputaciones en cadena
        # - prs_skip_balance_recompute: nuestro flag para PRS
        ctx = {
            'allowed_company_ids'             : [from_company.id],
            'skip_account_move_synchronization': True,
            'no_recompute'                     : True,
            'prs_skip_auto_reconcile'          : True,
        }

        line_vals = {
            'date'       : fields.Date.context_today(self),
            'payment_ref': texto,
            'amount'     : -abs(self.amount),
            'journal_id' : self.journal_id.id,
            'name'       : texto,
            'company_id' : from_company.id,
        }
        if self.partner_id:
            line_vals['partner_id'] = self.partner_id.id

        line_from = (
            self.env['account.bank.statement.line']
            .sudo()
            .with_company(from_company)
            .with_context(**ctx)
            .create(line_vals)
        )

        _logger.info(
            "PRS POS wizard: statement line %s creada en '%s' — "
            "queda 'Por revisar' esperando confirmación del admin.",
            line_from.id, self.journal_id.name,
        )

        # Registrar el depósito pendiente
        transfer = self.env['pos.cash.transfer'].sudo().create({
            'pos_session_id'        : self.pos_session_id.id,
            'date'                  : fields.Datetime.now(),
            'journal_id'            : self.journal_id.id,
            'destination_journal_id': dst_journal.id,
            'amount'                : self.amount,
            'currency_id'           : self.currency_id.id,
            'coupon_number'         : cup,
            'partner_id'            : self.partner_id.id if self.partner_id else False,
            'move_from_id'          : False,
            'move_to_id'            : False,
            'statement_line_from_id': line_from.id,
            'statement_line_to_id'  : False,
        })

        if self.pos_session_id:
            body = (
                "⏳ Depósito pendiente de validación — "
                "Cupón: %s — Importe: $%.2f — "
                "Destino: %s (requiere confirmación del administrador)"
            ) % (cup or '-', self.amount, dst_journal.display_name)
            self.pos_session_id.message_post(body=body, subtype_xmlid='mail.mt_note')

        return transfer
