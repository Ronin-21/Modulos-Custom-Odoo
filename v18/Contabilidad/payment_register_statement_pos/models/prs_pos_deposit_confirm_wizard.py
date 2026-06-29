# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PrsPosDepositConfirmWizard(models.TransientModel):
    _name = 'prs.pos.deposit.confirm.wizard'
    _description = 'Confirmar depósitos POS pendientes'

    journal_id = fields.Many2one(
        'account.journal', string='Caja destino', required=True, readonly=True,
    )
    deposit_ids = fields.Many2many('pos.cash.transfer', string='Depósitos pendientes')
    deposit_count = fields.Integer(compute='_compute_totals', string='Cantidad')
    total_amount  = fields.Monetary(
        compute='_compute_totals', string='Total a recibir',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one('res.currency', related='journal_id.currency_id')

    @api.depends('deposit_ids')
    def _compute_totals(self):
        for wiz in self:
            wiz.deposit_count = len(wiz.deposit_ids)
            wiz.total_amount  = sum(wiz.deposit_ids.mapped('amount'))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        journal_id = (
            ctx.get('default_journal_id')
            or ctx.get('active_journal_id')
            or ctx.get('journal_id')
        )
        if journal_id and 'deposit_ids' in fields_list:
            pending = self.env['pos.cash.transfer'].search([
                ('prs_pending_validation', '=', True),
                ('destination_journal_id', '=', journal_id),
            ])
            res['deposit_ids'] = [(6, 0, pending.ids)]
        return res

    def _build_success_action(self, count, total, journal_name):
        """Retorna la acción de éxito con reload del widget padre.

        El reload es necesario porque el widget de conciliación bancaria
        no sabe que se crearon nuevas statement lines — sin esto el usuario
        necesita F5 para verlas.
        """
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title'  : _('Depósitos confirmados'),
                'message': _(
                    "%(count)d depósito(s) confirmado(s) por $%(total).2f en %(journal)s."
                ) % {'count': count, 'total': total, 'journal': journal_name},
                'type'   : 'success',
                'sticky' : False,
                # Reload completo: el widget de conciliación no tiene
                # un mecanismo de refresh parcial accesible desde Python.
                'next'   : {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def action_confirm_selected(self):
        """Confirma solo los depósitos seleccionados en la lista."""
        self.ensure_one()
        if not self.deposit_ids:
            raise UserError(_('Seleccioná al menos un depósito para confirmar.'))

        self.deposit_ids.action_confirm_reception()

        return self._build_success_action(
            len(self.deposit_ids),
            self.total_amount,
            self.journal_id.display_name,
        )

    def action_confirm_all(self):
        """Confirma TODOS los depósitos pendientes del diario."""
        all_pending = self.env['pos.cash.transfer'].search([
            ('prs_pending_validation', '=', True),
            ('destination_journal_id', '=', self.journal_id.id),
        ])
        if not all_pending:
            raise UserError(_('No hay depósitos pendientes para confirmar.'))

        self.write({'deposit_ids': [(6, 0, all_pending.ids)]})
        return self.action_confirm_selected()
