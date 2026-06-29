# -*- coding: utf-8 -*-

import logging

from odoo import api, Command, fields, models, _
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class PrsInternalTransferWizard(models.TransientModel):
    _name = 'prs.internal.transfer.wizard'
    _description = 'Internal Transfer (Statement Lines)'

    source_journal_id = fields.Many2one(
        'account.journal',
        string='Diario origen',
        required=True,
        readonly=False,
    )
    destination_journal_id = fields.Many2one(
        'account.journal',
        string='Diario destino',
        required=True,
        domain=[('type', 'in', ('cash', 'bank'))],
    )
    include_in_last_statement = fields.Boolean(
        string='Incluir en último estado de cuenta',
        default=False,
        help='Si está activo, los extractos se asignarán al último Estado de Cuenta existente del diario.',
    )
    date = fields.Date(
        string='Fecha',
        required=True,
        default=fields.Date.context_today,
    )
    memo = fields.Char(string='Memo')
    currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_currency_id',
        readonly=True,
    )
    amount = fields.Monetary(
        string='Importe',
        required=True,
    )
    transfer_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de transferencia (liquidez)',
        required=True,
        default=lambda self: self._default_transfer_account_id(),
    )
    company_id = fields.Many2one(
        'res.company',
        compute='_compute_company_id',
        readonly=True,
    )

    # -------------------------------------------------------------------------
    # Domains / defaults
    # -------------------------------------------------------------------------

    def _domain_account_for_company(self, company):
        Account = self.env['account.account']
        if 'company_ids' in Account._fields:
            return [('company_ids', 'in', company.id)]
        if 'company_id' in Account._fields:
            return [('company_id', '=', company.id)]
        return []

    @api.onchange('source_journal_id')
    def _onchange_source_journal_id(self):
        if not self.source_journal_id:
            return
        company = self.source_journal_id.company_id
        # No se restringe el destino por company_id — se permiten transferencias
        # cross-company (ej. Caja Sucursal → Caja Central de otra empresa).
        domain = [
            ('type', 'in', ('cash', 'bank')),
            ('id', '!=', self.source_journal_id.id),
        ]
        return {'domain': {
            'destination_journal_id': domain,
            'transfer_account_id': self._domain_account_for_company(company),
        }}

    @api.depends('source_journal_id')
    def _compute_company_id(self):
        for wiz in self:
            wiz.company_id = wiz.source_journal_id.company_id

    @api.depends('source_journal_id')
    def _compute_currency_id(self):
        for wiz in self:
            journal = wiz.source_journal_id
            wiz.currency_id = journal.currency_id or journal.company_id.currency_id

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = dict(self.env.context or {})

        journal_id = (
            ctx.get('default_source_journal_id')
            or ctx.get('default_journal_id')
            or ctx.get('journal_id')
        )
        if not journal_id and ctx.get('active_model') == 'account.journal':
            journal_id = ctx.get('active_id')
        if not journal_id and ctx.get('active_model') == 'account.bank.statement.line':
            active_ids = ctx.get('active_ids') or (
                [] if not ctx.get('active_id') else [ctx.get('active_id')]
            )
            if active_ids:
                line = self.env['account.bank.statement.line'].browse(active_ids[0])
                if line and line.journal_id:
                    journal_id = line.journal_id.id

        if not res.get('source_journal_id') and journal_id:
            res['source_journal_id'] = journal_id

        if ('transfer_account_id' in fields_list
                and not res.get('transfer_account_id')
                and res.get('source_journal_id')):
            journal = self.env['account.journal'].browse(res['source_journal_id'])
            if journal and journal.company_id:
                res['transfer_account_id'] = self.with_company(
                    journal.company_id
                ).with_context(
                    allowed_company_ids=[journal.company_id.id]
                )._default_transfer_account_id()
        return res

    @api.model
    def _default_transfer_account_id(self):
        company = self.env.company
        candidate_fields = [
            'transfer_account_id',
            'internal_transfer_account_id',
            'account_internal_transfer_account_id',
            'account_journal_transfer_account_id',
            'liquidity_transfer_account_id',
        ]
        for fname in candidate_fields:
            if fname in company._fields:
                acc = company[fname]
                if acc:
                    return acc.id
        Account = self.env['account.account'].with_company(company)
        dom = self._domain_account_for_company(company) + [('name', 'ilike', 'Transferencia')]
        acc = Account.search(dom, limit=1)
        return acc.id

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_last_statement_for_journal(self, journal):
        Statement = self.env['account.bank.statement'].with_company(journal.company_id)
        if 'state' in Statement._fields:
            stmt = Statement.search(
                [('journal_id', '=', journal.id), ('state', 'not in', ('close', 'closed'))],
                order='date desc, id desc', limit=1,
            )
        else:
            stmt = Statement.browse()
        if not stmt:
            stmt = Statement.search(
                [('journal_id', '=', journal.id)],
                order='date desc, id desc', limit=1,
            )
        if not stmt:
            raise UserError(_(
                "No se encontró ningún Estado de Cuenta para el diario '%s'. "
                "Cree un extracto primero."
            ) % journal.display_name)
        return stmt

    def _create_statement_line(self, journal, amount, payment_ref, partner):
        """Crea una línea de extracto bancario.

        En Odoo 18, account.bank.statement.line usa _inherits de account.move.
        Al crear la línea, Odoo automáticamente crea el account.move con:
          - Línea de liquidez: cuenta bancaria del diario
          - Línea suspense:    cuenta transitoria/suspense del diario
        Y llama action_post() sobre ese move.
        NO creamos ningún move adicional aquí.
        """
        StatementLine = self.env['account.bank.statement.line'].with_company(journal.company_id)
        vals = {
            'journal_id': journal.id,
            'company_id': journal.company_id.id,
            'date': self.date,
            'payment_ref': payment_ref or '',
            'amount': amount,
        }
        if partner:
            vals['partner_id'] = partner.id

        if self.include_in_last_statement:
            statement = self._get_last_statement_for_journal(journal)
            vals['statement_id'] = statement.id
        else:
            vals['statement_id'] = False

        return StatementLine.create(vals)

    def _replace_suspense_with_transfer_account(self, statement_line):
        self.ensure_one()
        if not statement_line or not self.transfer_account_id:
            return

        if not self.transfer_account_id.reconcile:
            _logger.warning(
                "PRS: la cuenta de transferencia '%s' no tiene activada la "
                "reconciliación — los apuntes no podrán reconciliarse.",
                self.transfer_account_id.display_name,
            )

        try:
            statement_line.with_context(
                force_delete=True,
                skip_readonly_check=True,
            ).write({
                'line_ids': (
                    [Command.clear()]
                    + [
                        Command.create(line_vals)
                        for line_vals in statement_line._prepare_move_line_default_vals(
                            counterpart_account_id=self.transfer_account_id.id
                        )
                    ]
                ),
                'checked': True,
            })

            statement_line.move_id.with_context(
                skip_readonly_check=True,
            ).write({'checked': True})

            _logger.info(
                "PRS: suspense reemplazada por cuenta de transferencia en "
                "statement line %s (move %s).",
                statement_line.id, statement_line.move_id.name,
            )
        except Exception:
            _logger.exception(
                "PRS: ERROR al reemplazar la suspense line en statement line %s.",
                statement_line.id,
            )

    def _reconcile_transfer_account_lines(self, src_line, dst_line):
        """Reconcilia los apuntes de la cuenta de transferencia entre origen y destino.

        En transferencias mismo-empresa: reconcilia los dos apuntes entre sí.
        En transferencias cross-company: NO se reconcilian (son de distintas
        empresas y Odoo no permite reconciliación cross-company). Las líneas
        quedan con la cuenta de transferencia como contrapartida, lo cual es
        contablemente correcto — el balance de la cuenta se muestra por empresa.
        """
        source = self.source_journal_id
        dest = self.destination_journal_id

        if source.company_id != dest.company_id:
            _logger.info(
                "PRS: transferencia cross-company (%s → %s) — "
                "no se reconcilian los apuntes de transferencia entre empresas distintas.",
                source.company_id.name, dest.company_id.name,
            )
            return

        transfer_account = self.transfer_account_id
        src_aml = src_line.move_id.line_ids.filtered(
            lambda l: l.account_id == transfer_account
        )
        dst_aml = dst_line.move_id.line_ids.filtered(
            lambda l: l.account_id == transfer_account
        )
        if not src_aml or not dst_aml:
            _logger.warning(
                "PRS: no se encontraron apuntes de transferencia para reconciliar "
                "(src=%s, dst=%s).", src_line.id, dst_line.id,
            )
            return
        try:
            (src_aml + dst_aml).reconcile()
            _logger.info(
                "PRS: apuntes de transferencia reconciliados (%s ↔ %s).",
                src_aml.id, dst_aml.id,
            )
        except Exception:
            _logger.exception(
                "PRS: no se pudo reconciliar los apuntes de transferencia."
            )

    # -------------------------------------------------------------------------
    # Main action
    # -------------------------------------------------------------------------

    def action_confirm(self):
        self.ensure_one()

        if not self.source_journal_id or not self.destination_journal_id:
            raise UserError(_('Debe seleccionar el diario origen y el diario destino.'))
        if self.source_journal_id == self.destination_journal_id:
            raise UserError(_('El diario destino debe ser distinto al diario origen.'))
        if not self.amount or self.amount <= 0:
            raise UserError(_('El importe debe ser mayor a 0.'))

        source = self.source_journal_id
        dest = self.destination_journal_id

        # Se permiten transferencias cross-company (ej. Caja Sucursal → Caja Central).
        # Cada extracto se crea con el contexto de empresa de su propio diario.
        src_partner = source.company_id.partner_id
        dst_partner = dest.company_id.partner_id

        memo = self.memo or _('Transferencia interna')
        src_ref = _('%(memo)s → %(dest)s') % {'memo': memo, 'dest': dest.display_name}
        dst_ref = _('%(memo)s ← %(src)s') % {'memo': memo, 'src': source.display_name}

        try:
            # 1) Línea de extracto en origen (salida, negativa).
            src_line = self._create_statement_line(source, -self.amount, src_ref, src_partner)

            # 2) Reemplazar suspense del origen con la cuenta de transferencia.
            self._replace_suspense_with_transfer_account(src_line)

            # 3) Línea de extracto en destino (entrada, positiva).
            #    Se crea con la cuenta suspense del diario destino y queda
            #    en estado "Por revisar" — el operador del diario destino
            #    deberá validarla manualmente al confirmar la recepción.
            #    La reconciliación de la cuenta de transferencia tampoco se
            #    realiza automáticamente: ocurrirá cuando ambas partes validen.
            dst_line = self._create_statement_line(dest, self.amount, dst_ref, dst_partner)

            # 4) Marcar solo el origen como comprobado.
            #    El destino queda como "Por revisar" para que el operador confirme.
            try:
                src_line.move_id.with_context(skip_readonly_check=True).write(
                    {'checked': True}
                )
            except Exception:
                pass

        except Exception as e:
            _logger.exception(
                "PRS: error en transferencia interna %s → %s por $%s",
                source.name, dest.name, self.amount,
            )
            raise UserError(
                _("Ocurrió un error al procesar la transferencia interna: %s. "
                  "Verifique que los diarios tengan cuenta suspense y cuenta de "
                  "transferencia configuradas correctamente.") % str(e)
            ) from e

        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}