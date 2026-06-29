# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PrsCheckMassTransfer(models.TransientModel):
    _inherit = 'l10n_latam.payment.mass.transfer'
    _check_company_auto = False

    journal_id = fields.Many2one(
        'account.journal',
        compute='_compute_journal_company',
    )

    destination_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Destination Journal',
        domain="[('type', 'in', ('bank', 'cash'))]",
        required=True,
    )

    check_ids = fields.Many2many(
        'l10n_latam.check',
        'latam_tranfer_check_rel',
        'transfer_id',
        'check_id',
    )

    prs_is_cross_company = fields.Boolean(compute='_compute_prs_is_cross_company')
    prs_cross_company_warning = fields.Char(compute='_compute_prs_is_cross_company')

    @api.depends('journal_id', 'destination_journal_id')
    def _compute_prs_is_cross_company(self):
        for wiz in self:
            src = wiz.journal_id
            dst = wiz.destination_journal_id
            if src and dst and src.company_id != dst.company_id:
                wiz.prs_is_cross_company = True
                wiz.prs_cross_company_warning = (
                    "Transferencia entre empresas: %s → %s. "
                    "Los apuntes de la cuenta de transferencia no se reconciliarán automáticamente."
                    % (src.company_id.name, dst.company_id.name)
                )
            else:
                wiz.prs_is_cross_company = False
                wiz.prs_cross_company_warning = False

    def _create_payments(self):
        self.ensure_one()
        if self.journal_id.company_id == self.destination_journal_id.company_id:
            return super()._create_payments()
        return self._prs_create_cross_company_check_transfer()

    def _prs_create_cross_company_check_transfer(self):
        self.ensure_one()

        checks = self.check_ids.filtered(
            lambda x: x.payment_method_line_id.code == 'new_third_party_checks'
            and x.currency_id == self.check_ids[0].currency_id
        )
        if not checks:
            raise UserError(_("No se encontraron cheques válidos para transferir."))

        currency_id = checks[0].currency_id
        src_journal = self.journal_id
        dst_journal = self.destination_journal_id
        src_company = src_journal.company_id
        dst_company = dst_journal.company_id
        total_amount = sum(checks.mapped('amount'))

        _logger.info(
            "PRS: transferencia cross-company de cheques %s → %s por $%s (%s cheques)",
            src_company.name, dst_company.name, total_amount, len(checks),
        )

        # 1) Pago saliente en empresa origen
        pay_method_out = src_journal._get_available_payment_method_lines('outbound').filtered(
            lambda x: x.code in ('out_third_party_checks', 'return_third_party_checks')
        )[:1]

        outbound_payment = self.env['account.payment'].sudo().with_company(src_company).create({
            'date': self.payment_date,
            'amount': total_amount,
            'partner_id': src_company.partner_id.id,
            'payment_type': 'outbound',
            'memo': self.communication,
            'journal_id': src_journal.id,
            'currency_id': currency_id.id,
            'payment_method_line_id': pay_method_out.id if pay_method_out else False,
            'l10n_latam_move_check_ids': [Command.link(x.id) for x in checks],
        })
        outbound_payment.sudo().with_company(src_company).action_post()

        # 2) Pago entrante en empresa destino
        pay_method_in = dst_journal.inbound_payment_method_line_ids.filtered(
            lambda x: x.code == 'in_third_party_checks'
        )[:1]

        inbound_vals = {
            'date': self.payment_date,
            'amount': total_amount,
            'partner_id': dst_company.partner_id.id,
            'payment_type': 'inbound',
            'memo': self.communication,
            'journal_id': dst_journal.id,
            'currency_id': currency_id.id,
            'l10n_latam_move_check_ids': [Command.link(x.id) for x in checks],
        }
        if pay_method_in:
            inbound_vals['payment_method_line_id'] = pay_method_in.id

        inbound_payment = (
            self.env['account.payment']
            .sudo()
            .with_company(dst_company)
            .create(inbound_vals)
        )

        ctx_post = {'l10n_ar_skip_remove_check': True} if not pay_method_in else {}
        inbound_payment.sudo().with_company(dst_company).with_context(**ctx_post).action_post()

        # 3) Log en chatter
        inbound_payment.message_post(
            body=_("Transferencia cross-company desde: ") + outbound_payment._get_html_link()
        )
        outbound_payment.message_post(
            body=_("Transferencia cross-company hacia: ") + inbound_payment._get_html_link()
        )

        _logger.info(
            "PRS: completado. outbound=%s (%s), inbound=%s (%s). "
            "Apuntes intermedios NO reconciliados (cross-company).",
            outbound_payment.name, src_company.name,
            inbound_payment.name, dst_company.name,
        )

        return outbound_payment