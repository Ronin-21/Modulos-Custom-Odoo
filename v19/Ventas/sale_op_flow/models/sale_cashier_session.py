# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class SaleCashierSession(models.Model):
    _name = 'sale.cashier.session'
    _description = 'Sesión de Caja'
    _order = 'date desc, id desc'
    _rec_name = 'name'
    _inherit = ['mail.thread']

    name = fields.Char(string='Sesión', compute='_compute_name', store=True, readonly=True)
    cashier_id = fields.Many2one(
        'res.users', string='Cajero', required=True,
        default=lambda self: self.env.uid, tracking=True, index=True,
    )
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company, index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', store=True, readonly=True,
    )
    date = fields.Date(string='Fecha', required=True, default=fields.Date.today, index=True)
    state = fields.Selection(
        [('open', 'Abierta'), ('closed', 'Cerrada'),
         ('pending_validation', 'Pend. validación'), ('validated', 'Validada')],
        string='Estado', default='open', required=True, tracking=True, index=True,
    )
    opening_balance = fields.Monetary(
        string='Fondo inicial', default=0.0, currency_field='currency_id',
    )
    opening_date = fields.Datetime(string='Apertura', default=fields.Datetime.now, readonly=True)
    order_ids = fields.One2many('sale.order', 'cashier_session_id', string='Pedidos cobrados', readonly=True)
    total_orders = fields.Integer(string='Pedidos', compute='_compute_totals', store=True)
    total_collected = fields.Monetary(
        string='Total cobrado', compute='_compute_totals', store=True, currency_field='currency_id',
    )
    account_payment_ids = fields.One2many(
        'account.payment', 'op_cashier_session_id', string='Pagos de la sesión', readonly=True,
    )
    account_payment_cc_ids = fields.Many2many(
        'account.payment', compute='_compute_account_payments',
        string='Cobranzas a cuenta (pagos)',
        help='Solo los pagos a cuenta corriente (sin pedido) de la sesión.',
    )
    total_account_payments = fields.Monetary(
        string='Cobranzas a cuenta', compute='_compute_account_payments', store=True,
        currency_field='currency_id',
        help='Pagos a cuenta corriente cobrados en la sesión (no vinculados a un pedido). '
             'Entran a la caja y se rinden en el cierre.',
    )
    total_expected_rendition = fields.Monetary(
        string='Esperado rendición', compute='_compute_rendition_totals', store=True,
        currency_field='currency_id',
        help='Total esperado en rendición: cobros + fondo inicial de caja.',
    )
    line_ids = fields.One2many('sale.cashier.session.line', 'session_id', string='Rendición')
    total_real = fields.Monetary(
        string='Total rendido', compute='_compute_rendition_totals', store=True, currency_field='currency_id',
    )
    total_difference = fields.Monetary(
        string='Diferencia', compute='_compute_rendition_totals', store=True, currency_field='currency_id',
    )
    closed_date = fields.Datetime(string='Fecha cierre', readonly=True, copy=False)
    notes = fields.Text(string='Observaciones', copy=False)
    validated_by = fields.Many2one('res.users', string='Validado por', readonly=True, copy=False, tracking=True)
    validated_date = fields.Datetime(string='Fecha validación', readonly=True, copy=False)
    cash_difference_move_id = fields.Many2one(
        'account.move', string='Asiento de diferencia', readonly=True, copy=False,
        help='Primer asiento/línea de extracto creado por diferencias de rendición. Se conserva por compatibilidad.'
    )
    cash_difference_move_ids = fields.Many2many(
        'account.move',
        'sale_cashier_session_difference_move_rel',
        'session_id',
        'move_id',
        string='Asientos de diferencia',
        readonly=True,
        copy=False,
        help='Asientos o líneas de extracto creados por diferencias, separados por medio de pago.',
    )
    carry_over_amount = fields.Monetary(
        string='Fondo retenido (próx. sesión)',
        default=0.0,
        currency_field='currency_id',
        copy=False,
        help='Efectivo retenido al cierre para usar como fondo de la próxima sesión.',
    )
    cash_move_ids = fields.One2many(
        'sale.cashier.cash.move', 'session_id',
        string='Movimientos de efectivo',
    )
    total_cash_in = fields.Monetary(
        string='Total ingresos', compute='_compute_cash_moves',
        store=True, currency_field='currency_id',
    )
    total_cash_out = fields.Monetary(
        string='Total egresos', compute='_compute_cash_moves',
        store=True, currency_field='currency_id',
    )
    latam_check_count = fields.Integer(
        string='Cheques recibidos',
        compute='_compute_latam_check_stats',
    )
    latam_check_amount = fields.Monetary(
        string='Total cheques',
        compute='_compute_latam_check_stats',
        currency_field='currency_id',
    )
    can_do_cash_moves = fields.Boolean(
        compute='_compute_can_do_cash_moves',
        help='Indica si el usuario actual puede registrar ingresos/egresos de efectivo en esta sesión.',
    )

    def _compute_can_do_cash_moves(self):
        is_supervisor = self.env.user.has_group('sale_op_flow.group_sale_supervisor')
        if is_supervisor:
            for rec in self:
                rec.can_do_cash_moves = True
            return
        try:
            raw = self.env['ir.config_parameter'].sudo().get_param(
                'sale_op_flow.allow_cashier_cash_moves', '0')
            allowed = str(raw).lower() in ('1', 'true', 't', 'yes', 'y', 'on', 'si', 'sí')
        except Exception:
            allowed = False
        for rec in self:
            rec.can_do_cash_moves = allowed

    @api.depends('cashier_id', 'date')
    def _compute_name(self):
        for session in self:
            date_str = session.date.strftime('%d/%m/%Y') if session.date else '?'
            cashier_name = session.cashier_id.name or 'Cajero'
            if session._origin and session._origin.id:
                same_day = self.search([
                    ('cashier_id', '=', session.cashier_id.id),
                    ('date', '=', session.date),
                    ('id', '<=', session._origin.id),
                ])
                turno = len(same_day)
            else:
                turno = 1
            if turno > 1:
                session.name = f'Caja · {cashier_name} · {date_str} (T{turno})'
            else:
                session.name = f'Caja · {cashier_name} · {date_str}'

    @api.depends('order_ids', 'order_ids.operational_state')
    def _compute_totals(self):
        for session in self:
            session.total_orders = len(session.order_ids)
            paid_orders = session.order_ids.filtered(
                lambda o: o.operational_state in ('paid', 'dispatched')
            )
            total = 0.0
            if paid_orders:
                Payment = self.env['account.payment'].sudo()
                payments = Payment.search([
                    ('op_cashier_session_id', '=', session.id),
                    ('op_sale_order_id', '!=', False),
                    ('payment_type', '=', 'inbound'),
                    ('state', 'not in', ['draft', 'cancelled', 'canceled']),
                ])
                if not payments:
                    payments = Payment.search([
                        ('op_sale_order_id', 'in', paid_orders.ids),
                        ('payment_type', '=', 'inbound'),
                        ('state', 'not in', ['draft', 'cancelled', 'canceled']),
                    ])
                if payments:
                    total = sum(payments.mapped('amount'))
                else:
                    StmtLine = self.env['account.bank.statement.line'].sudo()
                    if 'payment_id' in StmtLine._fields:
                        lines = StmtLine.search([
                            ('payment_id.op_sale_order_id', 'in', paid_orders.ids),
                            ('amount', '>', 0),
                        ])
                        total = sum(lines.mapped('amount'))
            session.total_collected = total

    @api.depends('account_payment_ids', 'account_payment_ids.amount',
                 'account_payment_ids.state', 'account_payment_ids.op_sale_order_id',
                 'account_payment_ids.payment_type')
    def _compute_account_payments(self):
        for session in self:
            cc = session.account_payment_ids.filtered(
                lambda p: not p.op_sale_order_id
                and p.payment_type == 'inbound'
                and p.state not in ('draft', 'cancel', 'canceled', 'cancelled')
            )
            session.account_payment_cc_ids = cc
            session.total_account_payments = sum(cc.mapped('amount'))

    @api.depends('cash_move_ids.amount', 'cash_move_ids.move_type')
    def _compute_cash_moves(self):
        for session in self:
            ins = session.cash_move_ids.filtered(lambda m: m.move_type == 'in')
            outs = session.cash_move_ids.filtered(lambda m: m.move_type == 'out')
            session.total_cash_in = sum(ins.mapped('amount'))
            session.total_cash_out = sum(outs.mapped('amount'))

    @api.depends(
        'line_ids.amount_real', 'line_ids.amount_expected',
        'total_collected', 'total_account_payments', 'opening_balance',
        'total_cash_in', 'total_cash_out',
    )
    def _compute_rendition_totals(self):
        for session in self:
            if session.line_ids:
                # Sesión cerrada: tomar de las líneas de rendición
                expected = sum(session.line_ids.mapped('amount_expected'))
                real = sum(session.line_ids.mapped('amount_real'))
            else:
                # Sesión abierta: cobros de pedidos + cobranzas a cuenta + fondo inicial
                # + ingresos de caja - egresos
                expected = (
                    session.total_collected
                    + session.total_account_payments
                    + (session.opening_balance or 0.0)
                    + session.total_cash_in
                    - session.total_cash_out
                )
                real = 0.0
            session.total_expected_rendition = expected
            session.total_real = real
            session.total_difference = real - expected

    @api.constrains('cashier_id', 'state')
    def _check_unique_open_session(self):
        for session in self:
            if session.state == 'open':
                duplicate = self.search([
                    ('cashier_id', '=', session.cashier_id.id),
                    ('state', '=', 'open'),
                    ('id', '!=', session.id),
                ])
                if duplicate:
                    raise ValidationError(
                        _('El cajero "%s" ya tiene una sesión abierta: %s.')
                        % (session.cashier_id.name, duplicate[0].name)
                    )

    def _compute_latam_check_stats(self):
        Check = self.env['l10n_latam.check'] if 'l10n_latam.check' in self.env else None
        for session in self:
            if not Check:
                session.latam_check_count = 0
                session.latam_check_amount = 0.0
                continue
            payments = self.env['account.payment'].sudo().search([
                ('op_cashier_session_id', '=', session.id),
            ])
            checks = Check.sudo().search([('payment_id', 'in', payments.ids)])
            session.latam_check_count = len(checks)
            session.latam_check_amount = sum(checks.mapped('amount'))

    def action_open_latam_checks(self):
        self.ensure_one()
        payments = self.env['account.payment'].sudo().search([
            ('op_cashier_session_id', '=', self.id),
        ])
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cheques recibidos'),
            'res_model': 'l10n_latam.check',
            'view_mode': 'list,form',
            'domain': [('payment_id', 'in', payments.ids)],
            'context': {'create': False},
        }

    def action_open_cash_in_wizard(self):
        self.ensure_one()
        if self.state != 'open':
            raise UserError(_('Solo se pueden registrar movimientos en sesiones abiertas.'))
        if not self.can_do_cash_moves:
            raise UserError(_('No tenés permisos para registrar ingresos de efectivo.'))
        return {
            'name': _('Ingreso de Efectivo'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.cashier.cash.move.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_session_id': self.id, 'default_move_type': 'in'},
        }

    def action_open_cash_out_wizard(self):
        self.ensure_one()
        if self.state != 'open':
            raise UserError(_('Solo se pueden registrar movimientos en sesiones abiertas.'))
        if not self.can_do_cash_moves:
            raise UserError(_('No tenés permisos para registrar egresos de efectivo.'))
        return {
            'name': _('Egreso de Efectivo'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.cashier.cash.move.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_session_id': self.id, 'default_move_type': 'out'},
        }

    def action_validate_session(self):
        """Valida una rendición cerrada y contabiliza diferencias.

        Comportamiento inspirado en POS: la diferencia se calcula como
        Rendido - Esperado. Si es negativa, es faltante/pérdida; si es positiva,
        es sobrante/ganancia.
        """
        self.ensure_one()
        if not self.env.user.has_group('sale_op_flow.group_sale_supervisor'):
            raise UserError(_('Solo un supervisor puede validar sesiones.'))
        if self.state not in ('closed', 'pending_validation'):
            raise UserError(_('La sesión ya fue validada o no está cerrada.'))

        expected = sum(self.line_ids.mapped('amount_expected'))
        real = sum(self.line_ids.mapped('amount_real'))
        diff = real - expected
        if self.currency_id:
            expected = self.currency_id.round(expected)
            real = self.currency_id.round(real)
            diff = self.currency_id.round(diff)

        has_line_difference = any(
            not self.currency_id.is_zero(line.difference)
            for line in self.line_ids
        ) if self.currency_id else any(abs(line.difference) > 0.01 for line in self.line_ids)
        if has_line_difference:
            self._create_cash_difference_entries()

        self.write({
            'state': 'validated',
            'validated_by': self.env.uid,
            'validated_date': fields.Datetime.now(),
        })
        self.message_post(
            body=_('✅ Sesión validada por <b>%s</b>. Esperado: %.2f | Rendido: %.2f | Diferencia: %.2f')
            % (self.env.user.name, expected, real, diff)
        )

    def _config_bool(self, key, default='0'):
        value = self.env['ir.config_parameter'].sudo().get_param(f'sale_op_flow.{key}', default)
        return str(value).lower() in ('1', 'true', 't', 'yes', 'y', 'on', 'si', 'sí')

    def _get_config_record(self, model, key):
        get = self.env['ir.config_parameter'].sudo().get_param
        try:
            rid = int(get(f'sale_op_flow.{key}', '0') or 0)
        except Exception:
            rid = 0
        rec = self.env[model].sudo().browse(rid) if rid else self.env[model].sudo()
        return rec if rec and rec.exists() else self.env[model].sudo()

    def _get_difference_account(self, journal, difference):
        """Cuenta de pérdida/ganancia para una diferencia.

        Primero usa la configuración propia del módulo. Si no existe, cae a las
        cuentas nativas del diario (`loss_account_id` / `profit_account_id`),
        igual que POS.
        """
        if difference < 0:
            account = self._get_config_record('account.account', 'cash_difference_loss_account_id')
            if not account and journal and 'loss_account_id' in journal._fields:
                account = journal.loss_account_id
            if not account:
                raise UserError(_(
                    'Configurá la cuenta de pérdida/faltante en Configuración → Ajustes del flujo '
                    'o en el diario %s.'
                ) % (journal.display_name or journal.name))
            return account

        account = self._get_config_record('account.account', 'cash_difference_gain_account_id')
        if not account and journal and 'profit_account_id' in journal._fields:
            account = journal.profit_account_id
        if not account:
            raise UserError(_(
                'Configurá la cuenta de ganancia/sobrante en Configuración → Ajustes del flujo '
                'o en el diario %s.'
            ) % (journal.display_name or journal.name))
        return account

    def _get_difference_journal_for_line(self, line):
        """Diario donde contabilizar la diferencia de una línea de rendición.

        Criterio recomendado/POS-like: usar el mismo diario del medio de pago
        rendido. Así una diferencia de Efectivo afecta Efectivo, una diferencia
        de Banco afecta Banco, etc. El diario configurado queda solo como fallback
        o para instalaciones que quieran forzar un diario global.
        """
        use_payment_journal = self._config_bool('use_payment_journal_for_differences', '1')
        journal = line.payment_journal_id if use_payment_journal else self.env['account.journal']
        if not journal:
            journal = self._get_config_record('account.journal', 'cash_difference_journal_id')
        if not journal:
            raise UserError(_('No se pudo determinar el diario para contabilizar la diferencia.'))
        if journal.company_id and journal.company_id != self.company_id:
            raise UserError(_('El diario %s pertenece a otra empresa.') % journal.display_name)
        if not journal.default_account_id:
            raise UserError(_('El diario %s debe tener una cuenta por defecto.') % journal.display_name)
        return journal

    def _create_cash_difference_entries(self):
        """Contabiliza diferencias separadas por medio de pago.

        Si una sesión tiene efectivo, banco y tarjeta, cada diferencia se registra
        contra su propio diario. Esto evita usar una cuenta/diario genérico como
        "Diferencias de cambio" y evita compensar diferencias entre medios.
        """
        self.ensure_one()
        existing = self.cash_difference_move_ids or self.cash_difference_move_id
        if existing:
            return existing

        moves = self.env['account.move']
        lines = self.line_ids.filtered(lambda l: l.payment_journal_id and not self.currency_id.is_zero(l.difference))
        for line in lines:
            move = self._create_cash_difference_entry_for_line(line)
            if move:
                moves |= move

        if moves:
            self.write({
                'cash_difference_move_id': moves[0].id,
                'cash_difference_move_ids': [(6, 0, moves.ids)],
            })
        return moves

    def _create_cash_difference_entry(self, difference):
        """Compatibilidad con versiones anteriores.

        Antes se contabilizaba una única diferencia total con un diario global.
        Ahora se contabiliza por línea de rendición/medio de pago.
        """
        return self._create_cash_difference_entries()

    def _create_cash_difference_entry_for_line(self, line):
        self.ensure_one()
        difference = self.currency_id.round(line.difference) if self.currency_id else line.difference
        if self.currency_id and self.currency_id.is_zero(difference):
            return self.env['account.move']
        if not difference:
            return self.env['account.move']

        journal = self._get_difference_journal_for_line(line)
        diff_account = self._get_difference_account(journal, difference)
        amount = abs(difference)
        medio = line.payment_journal_id.display_name or line.payment_journal_id.name or journal.display_name
        label = (_('Faltante de caja — %(session)s — %(journal)s') if difference < 0 else _('Sobrante de caja — %(session)s — %(journal)s')) % {
            'session': self.name,
            'journal': medio,
        }

        # Diario financiero: crear línea de extracto contra la cuenta de pérdida/ganancia.
        # Esto replica mejor el comportamiento operativo del POS y además permite que
        # payment_register_statement_v19 auto-asigne la línea a un extracto abierto si
        # el diario tiene habilitado "Crear extractos automáticos".
        if journal.type in ('cash', 'bank', 'credit'):
            st_line_vals = {
                'journal_id': journal.id,
                'date': fields.Date.context_today(self),
                'amount': difference,
                'payment_ref': label,
                'counterpart_account_id': diff_account.id,
            }
            st_line = self.env['account.bank.statement.line'].sudo().with_company(self.company_id).with_context(
                no_retrieve_partner=True
            ).create(st_line_vals)
            move = st_line.move_id
            self.message_post(
                body=_('📒 Diferencia de %(medio)s contabilizada con línea de extracto: <b>%(move)s</b> | Importe: %(amount).2f') % {
                    'medio': medio,
                    'move': move.name or label,
                    'amount': difference,
                }
            )
            return move

        # Diario general/fallback: asiento directo contra la cuenta por defecto del diario.
        if difference < 0:
            lines = [
                (0, 0, {'account_id': diff_account.id, 'debit': amount, 'credit': 0.0, 'name': label}),
                (0, 0, {'account_id': journal.default_account_id.id, 'debit': 0.0, 'credit': amount, 'name': label}),
            ]
        else:
            lines = [
                (0, 0, {'account_id': journal.default_account_id.id, 'debit': amount, 'credit': 0.0, 'name': label}),
                (0, 0, {'account_id': diff_account.id, 'debit': 0.0, 'credit': amount, 'name': label}),
            ]
        move = self.env['account.move'].sudo().with_company(self.company_id).create({
            'journal_id': journal.id,
            'date': fields.Date.context_today(self),
            'ref': label,
            'line_ids': lines,
        })
        move.action_post()
        self.message_post(body=_('📒 Asiento de diferencia de %(medio)s creado: <b>%(move)s</b>') % {
            'medio': medio,
            'move': move.name or label,
        })
        return move

    def action_print_close_report(self):
        self.ensure_one()
        return self.env.ref('sale_op_flow.action_report_cashier_close_details').report_action(self)

    def action_open_close_wizard(self):
        """Abre el wizard de cierre. Solo el cajero dueño o el supervisor puede cerrar."""
        is_supervisor = self.env.user.has_group('sale_op_flow.group_sale_supervisor')
        if not is_supervisor and self.cashier_id.id != self.env.uid:
            raise UserError(_(
                'Solo podés cerrar tu propia sesión de caja.\n'
                'La sesión "%s" pertenece a %s.'
            ) % (self.name, self.cashier_id.name))

        self.ensure_one()
        if self.state != 'open':
            raise UserError(_('Esta sesión ya está cerrada o validada.'))

        # Bloquear cierre si hay pedidos sin cobrar en esta sesión
        pending_orders = self.env['sale.order'].search([
            ('cashier_session_id', '=', self.id),
            ('operational_state', 'in', ['confirmed', 'prepared']),
        ], order='name')
        if pending_orders:
            names = ', '.join(pending_orders.mapped('name'))
            raise UserError(_(
                'No podés cerrar la sesión con pedidos pendientes de cobro.\n\n'
                'Cobrá los siguientes pedidos antes de cerrar:\n%s'
            ) % names)
        return {
            'name': _('Cerrar sesión de caja'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.cashier.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_session_id': self.id},
        }

    def action_reopen_session(self):
        self.ensure_one()
        if not self.env.user.has_group('sale_op_flow.group_sale_supervisor'):
            raise UserError(_('Solo un supervisor puede reabrir sesiones.'))
        if self.state == 'validated':
            raise UserError(_('No se puede reabrir una sesión ya validada.'))
        duplicate = self.search([
            ('cashier_id', '=', self.cashier_id.id),
            ('state', '=', 'open'),
            ('id', '!=', self.id),
        ])
        if duplicate:
            raise UserError(
                _('El cajero ya tiene otra sesión abierta (%s). Ciérrela primero.') % duplicate[0].name
            )
        self.write({'state': 'open', 'closed_date': False, 'validated_by': False, 'validated_date': False})
        self.message_post(body=_('Reabierta por supervisor %s.') % self.env.user.name)

    def _sof_session_context(self):
        """Contexto común al entrar desde una tarjeta de sesión.

        La sesión puede haber sido creada por otro usuario (por ejemplo,
        Administrador), pero el cajero debe operar dentro de esa misma caja.
        default_is_sof_order=True garantiza que los pedidos creados desde
        este contexto usen el flujo SOF y no el flujo nativo de Odoo.
        """
        self.ensure_one()
        return {
            'sof_cashier_session_id': self.id,
            'default_cashier_session_id': self.id,
            'default_company_id': self.company_id.id,
            'default_is_sof_order': True,
            'allowed_company_ids': self.env.context.get('allowed_company_ids') or [self.company_id.id],
        }

    def action_open_new_quotation(self):
        """Abre directamente el formulario de nueva cotización."""
        self.ensure_one()
        ctx = {
            'default_operational_state': 'quotation',
            'default_company_id': self.company_id.id,
        }
        ctx.update(self._sof_session_context())
        return {
            'type': 'ir.actions.act_window',
            'name': 'Nueva Cotización',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'target': 'current',
            'context': ctx,
        }

    def action_open_quotations_list(self):
        """Desde la kanban de sesiones: abre las ventas de la empresa de esa sesión."""
        self.ensure_one()
        ctx = {
            'default_operational_state': 'quotation',
            'default_company_id': self.company_id.id,
            'create': True,
        }
        ctx.update(self._sof_session_context())
        return {
            'type': 'ir.actions.act_window',
            'name': 'Ventas',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'target': 'current',
            'domain': [
                ('is_sof_order', '=', True),
                ('company_id', '=', self.company_id.id),
                ('operational_state', 'in', ['quotation', 'confirmed']),
            ],
            'context': ctx,
        }

    def action_open_cashier_queue(self):
        """
        Desde la kanban de sesiones: el CAJERO entra a la sesión
        seleccionada y va directo a la cola de cobros de ESA sesión.
        Solo muestra pedidos vinculados a esta sesión específica.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pendientes de Cobro',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'target': 'current',
            'domain': [
                ('is_sof_order', '=', True),
                ('cashier_session_id', '=', self.id),
                ('operational_state', 'in', ['confirmed', 'prepared']),
            ],
            'context': dict(self._sof_session_context(), create=False),
        }

    @api.model
    def get_current_session(self):
        """Devuelve una sesión abierta disponible, aunque la haya abierto otro usuario."""
        Session = self.sudo()
        session = Session.search([
            ('state', '=', 'open'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not session:
            session = Session.search([('state', '=', 'open')], limit=1)
        if not session:
            raise UserError(
                _('No hay una sesión de caja abierta.\n'
                  'Abrí una desde Caja → Sesiones Abiertas → Nuevo.')
            )
        return session

