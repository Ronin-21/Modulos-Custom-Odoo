# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PrsLatamCheck(models.Model):
    """Extiende l10n_latam.check con campos PRS para cheques de terceros."""
    _inherit = 'l10n_latam.check'

    prs_third_party_state = fields.Selection(
        selection=[
            ('holding', 'En cartera'),
            ('cashed', 'Cobrado en efectivo'),
            ('endorsed', 'Entregado / Endosado'),
            ('deposited', 'Depositado'),
        ],
        string='Estado PRS',
        compute='_compute_prs_third_party_state',
        store=True,
        help=(
            "Estado del cheque de tercero:\n"
            "• En cartera: en un diario marcado como 'Diario de cheques de terceros'.\n"
            "• Cobrado en efectivo: transferido a una caja sin ese flag — cobrado en ventanilla.\n"
            "• Entregado/Endosado: entregado a proveedor o transferido sin depositar.\n"
            "• Depositado: ingresado a un diario bancario."
        ),
    )

    prs_endorsed_to_id = fields.Many2one(
        comodel_name='res.partner',
        string='Endosado a',
        compute='_compute_prs_endorsed_to_id',
        store=True,
        help="Persona o empresa a quien se entregó el cheque en su última operación saliente.",
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
                    # Diario marcado como cartera de cheques → en cartera
                    check.prs_third_party_state = 'holding'
                else:
                    # Caja de efectivo sin el flag → cobrado en ventanilla
                    check.prs_third_party_state = 'cashed'
                continue

            # Sin current_journal_id: el cheque salió de todos los diarios.
            last_out = self._prs_get_last_outbound_operation(check)
            if last_out and last_out.journal_id.type == 'bank':
                check.prs_third_party_state = 'deposited'
            else:
                check.prs_third_party_state = 'endorsed'

    @api.depends(
        'payment_method_line_id',
        'operation_ids.state',
        'operation_ids.payment_type',
        'operation_ids.partner_id',
        'payment_id.state',
    )
    def _compute_prs_endorsed_to_id(self):
        for check in self:
            if check.payment_method_line_id.code != 'new_third_party_checks':
                check.prs_endorsed_to_id = False
                continue
            # "Endosado a" solo tiene sentido cuando el cheque fue entregado
            # a un tercero como pago (estado 'endorsed').
            # Si está en cartera o depositado en banco, el campo no aplica.
            if check.prs_third_party_state != 'endorsed':
                check.prs_endorsed_to_id = False
                continue
            last_out = self._prs_get_last_outbound_operation(check)
            check.prs_endorsed_to_id = last_out.partner_id if last_out else False

    @staticmethod
    def _prs_get_last_outbound_operation(check):
        """Retorna el último pago saliente (outbound) validado del cheque."""
        ops = (check.payment_id + check.operation_ids).filtered(
            lambda p: p.state not in ('draft', 'cancel')
            and p.payment_type == 'outbound'
        ).sorted(key=lambda p: (p.date, p.write_date, p._origin.id))
        return ops[-1:] or False


class PrsCheckMassTransfer(models.TransientModel):
    """Extiende l10n_latam.payment.mass.transfer para transferencias
    cross-company de cheques de terceros entre sucursales.
    """
    _inherit = 'l10n_latam.payment.mass.transfer'
    _check_company_auto = False

    destination_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario destino',
        domain="[('type', 'in', ('bank', 'cash'))]",
        required=True,
        help=(
            "Diario al que se transferirán los cheques. "
            "Banco: el cheque queda depositado. "
            "Caja marcada como 'Diario de cheques de terceros': queda en cartera. "
            "Cualquier otra caja: queda cobrado en efectivo."
        ),
    )

    prs_is_cross_company = fields.Boolean(compute='_compute_prs_is_cross_company')
    prs_cross_company_warning = fields.Char(compute='_compute_prs_is_cross_company')

    @api.depends('journal_id', 'destination_journal_id')
    def _compute_prs_is_cross_company(self):
        for wiz in self:
            src, dst = wiz.journal_id, wiz.destination_journal_id
            if src and dst and src.company_id != dst.company_id:
                wiz.prs_is_cross_company = True
                wiz.prs_cross_company_warning = _(
                    "Transferencia entre empresas: %(src)s → %(dst)s. "
                    "Los apuntes no se reconciliarán automáticamente."
                ) % {'src': src.company_id.name, 'dst': dst.company_id.name}
            else:
                wiz.prs_is_cross_company = False
                wiz.prs_cross_company_warning = False

    def _create_payments(self):
        self.ensure_one()
        if self.journal_id.company_id == self.destination_journal_id.company_id:
            result = super()._create_payments()
            # Auto-reconciliar el extracto PRS cuando el destino es una caja de efectivo
            if self.destination_journal_id.type == 'cash' and not self.destination_journal_id.prs_check_journal:
                inbound = self._prs_get_inbound_cash_payment()
                if inbound:
                    self._prs_auto_reconcile_check_in_cash(inbound)
            return result
        return self._prs_create_cross_company_check_transfer()

    def _prs_get_inbound_cash_payment(self):
        """Busca el pago entrante recién creado por la transferencia en el diario destino.

        Usa búsqueda directa en DB por l10n_latam_move_check_ids para evitar
        problemas de caché ORM con operation_ids dentro de la misma transacción.
        """
        self.ensure_one()
        if not self.check_ids:
            return self.env['account.payment']
        # Búsqueda directa en DB: pago inbound más reciente en destino vinculado a los cheques
        inbound = self.env['account.payment'].search([
            ('journal_id', '=', self.destination_journal_id.id),
            ('payment_type', '=', 'inbound'),
            ('date', '=', self.payment_date),
            ('state', 'not in', ('draft', 'cancel')),
            ('l10n_latam_move_check_ids', 'in', self.check_ids.ids),
        ], order='id desc', limit=1)
        if not inbound:
            _logger.warning(
                "PRS-AR: no se encontró pago inbound en %s para los cheques %s",
                self.destination_journal_id.name, self.check_ids.mapped('name'),
            )
        return inbound

    def _prs_auto_reconcile_check_in_cash(self, inbound_payment):
        """Reconcilia automáticamente la línea de extracto PRS con el pago en caja.

        Flujo Odoo 18:
        1. El extracto PRS tiene: Caja(débito) / Bank Suspense Account(crédito)
        2. El pago tiene: Outstanding Receipts(débito) / Liquidity Transfer(crédito, ya reconciliado)
        3. Reemplazamos Suspense → cuenta Outstanding Receipts en el extracto
        4. Reconciliamos la nueva línea del extracto con la línea Outstanding del pago
           → el pago pasa automáticamente de "En proceso" a "Pagado"
        """
        self.ensure_one()
        journal = inbound_payment.journal_id
        if not getattr(journal, 'auto_extract_enabled', False):
            return

        # Los extractos PRS se crean en la empresa del diario (journal.company_id),
        # que puede diferir de la empresa activa en la env del wizard. Usar sudo()
        # en el modelo para que el search no sea filtrado por la empresa incorrecta.
        self.env.flush_all()

        # Buscar la línea de extracto PRS creada para este pago
        st_line = self.env['account.bank.statement.line'].sudo().search([
            ('payment_id', '=', inbound_payment.id),
            ('journal_id', '=', journal.id),
        ], limit=1)
        if not st_line or st_line.is_reconciled:
            _logger.info("PRS-AR: sin extracto pendiente para pago %s — reconciliación omitida", inbound_payment.name)
            return

        # Línea Outstanding Receipts del pago (conciliable, sin reconciliar, no es caja ni suspense)
        outstanding_line = self.env['account.move.line'].sudo().search([
            ('move_id', '=', inbound_payment.move_id.id),
            ('account_id.reconcile', '=', True),
            ('reconciled', '=', False),
            ('account_id', '!=', journal.suspense_account_id.id),
            ('account_id', '!=', journal.default_account_id.id),
        ], limit=1)
        if not outstanding_line:
            _logger.warning(
                "PRS-AR: pago %s sin línea Outstanding Receipts — reconciliación omitida",
                inbound_payment.name,
            )
            return

        # Línea Suspense del extracto a reemplazar
        _, suspense_lines, _ = st_line._seek_for_lines()
        if not suspense_lines:
            _logger.info("PRS-AR: extracto %s ya sin línea suspense — reconciliación omitida", st_line.id)
            return

        try:
            # Reemplazar Suspense por la cuenta Outstanding Receipts en el move del extracto.
            # El extracto es inbound → la línea suspense es crédito, la nueva también es crédito.
            st_line.move_id.with_context(
                force_delete=True,
                skip_readonly_check=True,
                skip_account_move_synchronization=True,
            ).write({
                'line_ids': [
                    Command.delete(suspense_lines[0].id),
                    Command.create({
                        'name': outstanding_line.name or inbound_payment.name,
                        'account_id': outstanding_line.account_id.id,
                        'partner_id': outstanding_line.partner_id.id if outstanding_line.partner_id else False,
                        'debit': outstanding_line.credit,
                        'credit': outstanding_line.debit,
                        'currency_id': outstanding_line.currency_id.id,
                        'amount_currency': -outstanding_line.amount_currency,
                    }),
                ],
            })

            # Flush a DB y limpiar caché ORM antes de buscar la nueva línea.
            # Sin esto, st_line.move_id.line_ids puede devolver el estado previo al write.
            self.env.flush_all()
            st_line.move_id.invalidate_recordset(['line_ids'])

            # Buscar la nueva línea Outstanding directamente desde DB (no desde caché ORM).
            # Usar sudo() porque el move del extracto es de la empresa del diario, no del wizard.
            new_line = self.env['account.move.line'].sudo().search([
                ('move_id', '=', st_line.move_id.id),
                ('account_id', '=', outstanding_line.account_id.id),
                ('reconciled', '=', False),
            ], limit=1)

            if not new_line:
                _logger.warning(
                    "PRS-AR: no se encontró la nueva línea Outstanding en extracto %s",
                    st_line.id,
                )
                return

            (new_line + outstanding_line).reconcile()
            _logger.info(
                "PRS-AR: cheque en caja reconciliado. pago=%s extracto=%s — pago pasa a Pagado",
                inbound_payment.name, st_line.id,
            )

        except Exception:
            _logger.warning(
                "PRS-AR: reconciliación automática falló para pago %s",
                inbound_payment.name,
                exc_info=True,
            )

    def _prs_create_cross_company_check_transfer(self):
        """Crea la transferencia de cheques entre dos empresas distintas.

        Flujo:
        1. Pago SALIENTE en empresa origen  → cheque sale de cartera
        2. Pago ENTRANTE en empresa destino → cheque aparece en destino
        3. Auto-reconcilia si el destino es caja de efectivo (no cartera)
        4. Log en chatter de ambos pagos

        Los apuntes contables cross-company NO se reconcilian entre sí.
        """
        self.ensure_one()
        checks = self.check_ids.filtered(
            lambda c: c.payment_method_line_id.code == 'new_third_party_checks'
            and c.currency_id == self.check_ids[0].currency_id
        )
        if not checks:
            raise UserError(_(
                "No se encontraron cheques de terceros válidos. "
                "Solo se transfieren cheques recibidos (new_third_party_checks) en la misma moneda."
            ))

        currency = checks[0].currency_id
        src_journal, dst_journal = self.journal_id, self.destination_journal_id
        src_company, dst_company = src_journal.company_id, dst_journal.company_id
        total_amount = sum(checks.mapped('amount'))

        _logger.info(
            "PRS-AR: cross-company %d cheque(s) %s→%s $%s %s",
            len(checks), src_company.name, dst_company.name, total_amount, currency.name,
        )

        # 1) Pago saliente en empresa origen
        pay_method_out = src_journal._get_available_payment_method_lines('outbound').filtered(
            lambda x: x.code in ('out_third_party_checks', 'return_third_party_checks')
        )[:1]
        if not pay_method_out:
            raise UserError(_(
                "El diario '%s' no tiene método de salida para cheques de terceros."
            ) % src_journal.display_name)

        outbound = (
            self.env['account.payment'].sudo().with_company(src_company).create({
                'date': self.payment_date,
                'amount': total_amount,
                'partner_id': dst_company.partner_id.id,
                'payment_type': 'outbound',
                'memo': self.communication,
                'journal_id': src_journal.id,
                'currency_id': currency.id,
                'payment_method_line_id': pay_method_out.id,
                'l10n_latam_move_check_ids': [Command.link(c.id) for c in checks],
            })
        )
        outbound.sudo().with_company(src_company).action_post()

        # 2) Pago entrante en empresa destino
        pay_method_in = dst_journal.inbound_payment_method_line_ids.filtered(
            lambda x: x.code == 'in_third_party_checks'
        )[:1]

        inbound_vals = {
            'date': self.payment_date,
            'amount': total_amount,
            'partner_id': src_company.partner_id.id,
            'payment_type': 'inbound',
            'memo': self.communication,
            'journal_id': dst_journal.id,
            'currency_id': currency.id,
            'l10n_latam_move_check_ids': [Command.link(c.id) for c in checks],
        }
        if pay_method_in:
            inbound_vals['payment_method_line_id'] = pay_method_in.id

        inbound = (
            self.env['account.payment'].sudo().with_company(dst_company).create(inbound_vals)
        )
        ctx = {'l10n_ar_skip_remove_check': True} if not pay_method_in else {}
        inbound.sudo().with_company(dst_company).with_context(**ctx).action_post()

        # 3) Auto-reconciliar si el destino es una caja de efectivo (no cartera de cheques)
        if dst_journal.type == 'cash' and not dst_journal.prs_check_journal:
            self._prs_auto_reconcile_check_in_cash(inbound)

        # 4) Log cruzado en chatter
        inbound.message_post(
            body=_("Transferencia cross-company recibida desde: ") + outbound._get_html_link()
        )
        outbound.message_post(
            body=_("Transferencia cross-company enviada hacia: ") + inbound._get_html_link()
        )

        _logger.info("PRS-AR: out=%s(%s) → in=%s(%s)",
                     outbound.name, src_company.name, inbound.name, dst_company.name)
        return outbound
