# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PrsLatamCheck(models.Model):
    """Extiende l10n_latam.check con estado correcto para cheques de terceros.

    Odoo calcula issue_state solo para cheques propios (outstanding_line_id),
    por lo que el filtro nativo 'A la mano' nunca muestra cheques de terceros.
    prs_third_party_state resuelve esto usando current_journal_id y el historial
    de operaciones para determinar dónde está el cheque.
    """
    _inherit = 'l10n_latam.check'

    prs_third_party_state = fields.Selection(
        selection=[
            ('holding', 'En cartera'),
            ('cashed', 'Cobrado en efectivo'),
            ('endorsed', 'Entregado / Endosado'),
            ('deposited', 'Depositado'),
        ],
        string='Estado',
        compute='_compute_prs_third_party_state',
        store=True,
        help=(
            "Estado del cheque de tercero:\n"
            "• En cartera: en un diario marcado como 'Diario de cheques de terceros'.\n"
            "• Cobrado en efectivo: transferido a un diario de caja sin ese flag — "
            "cobrado en ventanilla.\n"
            "• Depositado: ingresado a un diario bancario.\n"
            "• Entregado/Endosado: salió de todos los diarios — entregado a proveedor."
        ),
    )

    prs_endorsed_to_id = fields.Many2one(
        comodel_name='res.partner',
        string='Endosado a',
        compute='_compute_prs_endorsed_to_id',
        store=True,
        help='Persona o empresa a quien se entregó el cheque en su última operación saliente.',
    )

    @api.depends(
        'payment_method_line_id',
        'current_journal_id',
        'current_journal_id.type',
        'current_journal_id.prs_check_journal',
        'operation_ids.state',
        'operation_ids.payment_type',
        'operation_ids.journal_id',
        'operation_ids.journal_id.type',
        'payment_id.state',
    )
    def _compute_prs_third_party_state(self):
        for check in self:
            if check.payment_method_line_id.code != 'new_third_party_checks':
                check.prs_third_party_state = False
                continue

            journal = check.current_journal_id
            if journal:
                if journal.type == 'bank':
                    check.prs_third_party_state = 'deposited'
                elif journal.prs_check_journal:
                    # Diario de cartera de cheques → en cartera
                    check.prs_third_party_state = 'holding'
                else:
                    # Diario de caja sin flag → cobrado en ventanilla
                    check.prs_third_party_state = 'cashed'
                continue

            # Sin current_journal_id: salió de todos los diarios.
            last_out = self._prs_get_last_outbound_op(check)
            check.prs_third_party_state = (
                'deposited' if last_out and last_out.journal_id.type == 'bank'
                else 'endorsed'
            )

    @api.depends(
        'payment_method_line_id',
        'prs_third_party_state',
        'operation_ids.state',
        'operation_ids.payment_type',
        'operation_ids.partner_id',
        'payment_id.state',
    )
    def _compute_prs_endorsed_to_id(self):
        for check in self:
            if (
                check.payment_method_line_id.code != 'new_third_party_checks'
                or check.prs_third_party_state != 'endorsed'
            ):
                check.prs_endorsed_to_id = False
                continue
            last_out = self._prs_get_last_outbound_op(check)
            check.prs_endorsed_to_id = last_out.partner_id if last_out else False

    @staticmethod
    def _prs_get_last_outbound_op(check):
        """Último pago saliente validado del cheque (historial de operaciones)."""
        ops = (check.payment_id + check.operation_ids).filtered(
            lambda p: p.state not in ('draft', 'canceled') and p.payment_type == 'outbound'
        ).sorted(key=lambda p: (p.date, p.write_date, p._origin.id))
        return ops[-1:] or False
