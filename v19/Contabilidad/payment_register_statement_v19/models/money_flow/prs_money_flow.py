# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)


class PrsMoneyFlow(models.Model):
    _name = 'prs.money.flow'
    _description = 'Flujo de Dinero PRS'
    _order = 'expected_date asc, journal_id, id'
    _check_company_auto = True

    name = fields.Char(string='Referencia', compute='_compute_name', store=True, readonly=False)
    unique_key = fields.Char(string='Clave unica PRS', index=True, copy=False)

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario de impacto',
        required=True,
        check_company=True,
        index=True,
    )
    partner_id = fields.Many2one('res.partner', string='Contacto', index=True)
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        required=True,
        default=lambda self: self.env.company.currency_id,
    )

    source_model = fields.Char(string='Modelo origen', index=True, copy=False)
    source_res_id = fields.Integer(string='ID origen', index=True, copy=False)
    source_display_name = fields.Char(string='Origen', compute='_compute_source_display_name')
    payment_id = fields.Many2one('account.payment', string='Pago origen', readonly=True, index=True, ondelete='set null')
    statement_line_id = fields.Many2one(
        'account.bank.statement.line',
        string='Linea de extracto',
        readonly=True,
        index=True,
        ondelete='set null',
    )
    statement_id = fields.Many2one(
        'account.bank.statement',
        string='Estado de cuenta',
        related='statement_line_id.statement_id',
        store=True,
        readonly=True,
    )

    flow_type = fields.Selection(
        selection=[
            ('payment', 'Pago'),
            ('check_in', 'Cheque recibido'),
            ('check_out', 'Cheque emitido'),
            ('check_endorsed_out', 'Cheque entregado/endosado'),
            ('pos_card', 'Tarjeta POS'),
            ('pos_qr', 'QR / billetera POS'),
            ('pos_cash', 'Efectivo POS'),
            ('manual_forecast', 'Prevision manual'),
            ('other', 'Otro'),
        ],
        string='Tipo',
        required=True,
        default='payment',
        index=True,
    )
    direction = fields.Selection(
        selection=[('inbound', 'Entrada'), ('outbound', 'Salida')],
        string='Direccion',
        required=True,
        default='inbound',
        index=True,
    )
    label = fields.Char(string='Etiqueta', required=True, index=True)
    origin_date = fields.Date(string='Fecha origen', required=True, default=fields.Date.context_today, index=True)
    expected_date = fields.Date(string='Fecha esperada', required=True, default=fields.Date.context_today, index=True)
    actual_date = fields.Date(string='Fecha real', copy=False)

    amount_gross = fields.Monetary(string='Bruto', currency_field='currency_id', required=True, default=0.0)
    fee_amount = fields.Monetary(string='Comision', currency_field='currency_id', default=0.0)
    fee_tax_amount = fields.Monetary(string='IVA comision', currency_field='currency_id', default=0.0)
    withholding_amount = fields.Monetary(string='Retenciones/Percepciones', currency_field='currency_id', default=0.0)
    amount_net = fields.Monetary(
        string='Neto',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True,
        readonly=False,
    )
    amount_signed = fields.Monetary(
        string='Importe con signo',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True,
    )

    auto_create_statement = fields.Boolean(string='Crear extracto automaticamente', default=True)
    projection_only = fields.Boolean(string='Solo proyeccion', default=False)
    state = fields.Selection(
        selection=[
            ('planned', 'Proyectado'),
            ('due', 'Vencido'),
            ('waiting_accreditation', 'Esperando acreditacion'),
            ('statement_created', 'Extracto creado'),
            ('reconciled', 'Conciliado'),
            ('manual_review', 'Revision manual'),
            ('cancelled', 'Cancelado'),
            ('rejected', 'Rechazado'),
        ],
        string='Estado',
        default='planned',
        required=True,
        index=True,
        copy=False,
    )
    note = fields.Text(string='Notas')

    flow_group = fields.Selection(
        [('inbound', 'Ingresos'), ('outbound', 'Egresos')],
        string='Grupo',
        compute='_compute_flow_group',
        store=True,
        index=True,
    )
    source_tag = fields.Char(
        string='Agrupador',
        index=True,
        help='Etiqueta de agrupacion para reportes de Flujo de Dinero. Las extensiones POS/AR la completan con tarjeta, QR, cheques, etc.',
    )
    payment_method_label = fields.Char(string='Medio de pago', index=True)
    card_label = fields.Char(string='Tarjeta / Marca', index=True)
    plan_label = fields.Char(string='Plan', index=True)
    pos_config_label = fields.Char(string='Punto de venta', index=True)
    calendar_all_day = fields.Boolean(string='Todo el dia', default=True)


    _sql_constraints = [
        (
            'unique_key_company_uniq',
            'unique(company_id, unique_key)',
            'Ya existe un flujo de dinero con la misma clave unica para esta empresa.',
        ),
    ]

    @api.depends('direction')
    def _compute_flow_group(self):
        for flow in self:
            flow.flow_group = 'outbound' if flow.direction == 'outbound' else 'inbound'

    @api.model
    def _prs_default_source_tag_from_vals(self, vals):
        flow_type = vals.get('flow_type') or 'payment'
        mapping = {
            'payment': _('Pagos'),
            'check_in': _('Cheques en cartera / deposito'),
            'check_out': _('Cheques propios pendientes'),
            'check_endorsed_out': _('Cheques de terceros entregados'),
            'pos_card': _('Tarjetas POS'),
            'pos_qr': _('QR / billeteras POS'),
            'pos_cash': _('Efectivo POS'),
            'manual_forecast': _('Previsiones'),
            'other': _('Otros'),
        }
        return mapping.get(flow_type, _('Otros'))

    @api.depends('label', 'expected_date', 'journal_id')
    def _compute_name(self):
        for flow in self:
            if flow.label:
                flow.name = flow.label
            elif flow.journal_id and flow.expected_date:
                flow.name = '%s - %s' % (flow.journal_id.display_name, flow.expected_date)
            else:
                flow.name = _('Flujo de dinero')

    @api.depends('source_model', 'source_res_id')
    def _compute_source_display_name(self):
        for flow in self:
            display = False
            if flow.source_model and flow.source_res_id and flow.source_model in self.env:
                record = self.env[flow.source_model].browse(flow.source_res_id).exists()
                if record:
                    display = record.display_name
            flow.source_display_name = display or flow.payment_id.display_name or False

    @api.depends('amount_gross', 'fee_amount', 'fee_tax_amount', 'withholding_amount', 'direction')
    def _compute_amounts(self):
        for flow in self:
            gross = flow.amount_gross or 0.0
            deductions = (flow.fee_amount or 0.0) + (flow.fee_tax_amount or 0.0) + (flow.withholding_amount or 0.0)
            net = gross - deductions
            flow.amount_net = net
            sign = 1.0 if flow.direction == 'inbound' else -1.0
            flow.amount_signed = sign * net

    @api.constrains('company_id', 'journal_id')
    def _check_company_journal(self):
        for flow in self:
            if flow.journal_id and flow.company_id and flow.journal_id.company_id != flow.company_id:
                raise ValidationError(_('El diario del flujo debe pertenecer a la empresa de impacto del flujo.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('journal_id') and not vals.get('company_id'):
                journal = self.env['account.journal'].browse(vals['journal_id'])
                vals['company_id'] = journal.company_id.id
            if vals.get('company_id') and not vals.get('currency_id'):
                vals['currency_id'] = self.env['res.company'].browse(vals['company_id']).currency_id.id
            if not vals.get('source_tag'):
                vals['source_tag'] = self._prs_default_source_tag_from_vals(vals)
            if not vals.get('payment_method_label'):
                vals['payment_method_label'] = vals.get('source_tag')
            if not vals.get('unique_key'):
                vals['unique_key'] = self._prs_make_unique_key(vals)
        return super().create(vals_list)

    @api.model
    def _prs_make_unique_key(self, vals):
        source_model = vals.get('source_model') or ('account.payment' if vals.get('payment_id') else False)
        source_res_id = vals.get('source_res_id') or vals.get('payment_id') or ''
        if not source_model or not source_res_id:
            return False
        parts = [
            source_model,
            str(source_res_id),
            vals.get('flow_type') or 'payment',
            vals.get('direction') or 'inbound',
            str(vals.get('journal_id') or ''),
            str(vals.get('expected_date') or ''),
        ]
        return ':'.join(parts)

    @api.model
    def _prs_create_or_get(self, vals):
        vals = dict(vals or {})
        if vals.get('journal_id') and not vals.get('company_id'):
            journal = self.env['account.journal'].browse(vals['journal_id'])
            vals['company_id'] = journal.company_id.id
        if not vals.get('unique_key'):
            vals['unique_key'] = self._prs_make_unique_key(vals)
        unique_key = vals.get('unique_key')
        if unique_key and vals.get('company_id'):
            existing = self.search([
                ('company_id', '=', vals['company_id']),
                ('unique_key', '=', unique_key),
            ], limit=1)
            if existing:
                updatable_states = ('planned', 'due', 'waiting_accreditation', 'manual_review')
                if existing.state in updatable_states and not existing.statement_line_id:
                    safe_vals = {
                        key: value for key, value in vals.items()
                        if key not in ('unique_key', 'company_id')
                    }
                    if safe_vals:
                        existing.write(safe_vals)
                return existing
        return self.create(vals)

    def _prs_prepare_statement_line_vals(self):
        self.ensure_one()
        date = self.actual_date or self.expected_date or fields.Date.context_today(self)
        amount = self.amount_signed
        label = self.label or self.name or _('Flujo de dinero')
        vals = {
            'date': date,
            'payment_ref': label,
            'amount': amount,
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
        }
        Line = self.env['account.bank.statement.line']
        if 'name' in Line._fields:
            vals['name'] = label
        if self.partner_id:
            vals['partner_id'] = self.partner_id.id
        if 'prs_money_flow_id' in Line._fields:
            vals['prs_money_flow_id'] = self.id
        if self.payment_id and 'payment_id' in Line._fields:
            vals['payment_id'] = self.payment_id.id

        company_currency = self.company_id.currency_id
        if self.currency_id and self.currency_id != company_currency:
            if 'foreign_currency_id' in Line._fields:
                vals['foreign_currency_id'] = self.currency_id.id
            if 'amount_currency' in Line._fields:
                vals['amount_currency'] = amount

        statement = self._prs_get_statement_for_date(date)
        if statement:
            vals['statement_id'] = statement.id
        return vals

    def _prs_get_statement_for_date(self, date):
        self.ensure_one()
        policy = self.journal_id.prs_flow_statement_policy or 'daily'
        if policy == 'none':
            return False
        if getattr(self, 'payment_id', False) and getattr(self.payment_id, 'prs_statement_id', False):
            statement = self.payment_id.prs_statement_id
            if statement.journal_id == self.journal_id:
                return statement
        Statement = self.env['account.bank.statement'].sudo().with_company(self.company_id)
        domain = [('journal_id', '=', self.journal_id.id)]
        if 'prs_state' in Statement._fields:
            open_domain = [('prs_state', '=', 'open')]
        elif 'state' in Statement._fields:
            open_domain = [('state', 'not in', ('close', 'closed'))]
        else:
            open_domain = []
        if policy == 'daily':
            exact_domain = domain + [('date', '=', date)] + open_domain
            statement = Statement.search(exact_domain, order='id desc', limit=1)
            if statement:
                return statement
            return self._prs_create_statement_for_date(date)
        statement = Statement.search(domain + open_domain, order='date desc, id desc', limit=1)
        return statement or False

    def _prs_create_statement_for_date(self, date):
        self.ensure_one()
        Statement = self.env['account.bank.statement'].sudo().with_company(self.company_id)
        journal = self.journal_id
        name = '%s - %s' % (journal.code or journal.name, date)
        last = Statement.search([
            ('journal_id', '=', journal.id),
            ('date', '<', date),
        ], order='date desc, id desc', limit=1)
        balance_start = 0.0
        if last:
            balance_start = (
                getattr(last, 'balance_end_real', False)
                or getattr(last, 'balance_end', False)
                or getattr(last, 'balance_start', 0.0)
                or 0.0
            )
        vals = {
            'name': name,
            'journal_id': journal.id,
            'date': date,
            'company_id': self.company_id.id,
        }
        if 'balance_start' in Statement._fields:
            vals['balance_start'] = balance_start
        if 'prs_state' in Statement._fields:
            vals['prs_state'] = 'open'
        try:
            return Statement.create(vals)
        except Exception as exc:
            _logger.warning('PRS: no se pudo crear estado de cuenta diario %s/%s: %s', journal.display_name, date, exc)
            return False

    def _prs_should_create_statement_now(self):
        self.ensure_one()
        if self.projection_only or not self.auto_create_statement:
            return False
        if self.statement_line_id:
            return False
        if self.state in ('cancelled', 'rejected', 'statement_created', 'reconciled'):
            return False
        today = fields.Date.context_today(self)
        return bool(self.expected_date and self.expected_date <= today)

    def action_create_statement_line(self):
        Line = self.env['account.bank.statement.line']
        for flow in self:
            if flow.statement_line_id:
                continue
            if flow.projection_only:
                flow.state = 'manual_review'
                continue
            if flow.state in ('cancelled', 'rejected'):
                continue
            if float_is_zero(flow.amount_signed, precision_rounding=flow.currency_id.rounding):
                flow.state = 'manual_review'
                continue
            vals = flow._prs_prepare_statement_line_vals()
            line = (
                Line.sudo()
                .with_company(flow.company_id)
                .with_context(allowed_company_ids=[flow.company_id.id])
                .create(vals)
            )
            flow.write({
                'statement_line_id': line.id,
                'state': 'statement_created',
                'actual_date': vals.get('date'),
            })
            statement = line.statement_id
            if statement:
                try:
                    if getattr(statement.journal_id, 'prs_auto_statement_balance', False) and hasattr(statement, '_prs_recompute_balances'):
                        statement._prs_recompute_balances(start_from=statement)
                    elif hasattr(statement, '_compute_balance_end_real'):
                        statement._compute_balance_end_real()
                except Exception:
                    pass
        return True

    def action_mark_due(self):
        for flow in self.filtered(lambda f: f.state == 'planned'):
            flow.state = 'due'
        return True

    def action_cancel(self):
        for flow in self:
            if flow.statement_line_id and getattr(flow.statement_line_id, 'is_reconciled', False):
                raise UserError(_('No se puede cancelar un flujo cuyo extracto ya esta conciliado.'))
            flow.state = 'cancelled'
        return True

    def action_reset_to_planned(self):
        for flow in self:
            if flow.statement_line_id:
                raise UserError(_('No se puede volver a proyectado un flujo que ya tiene extracto.'))
            flow.state = 'planned'
        return True

    def action_open_source(self):
        self.ensure_one()
        if not self.source_model or not self.source_res_id or self.source_model not in self.env:
            return False
        record = self.env[self.source_model].browse(self.source_res_id).exists()
        if not record:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': record.display_name,
            'res_model': self.source_model,
            'res_id': record.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_statement_line(self):
        self.ensure_one()
        if not self.statement_line_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': self.statement_line_id.display_name,
            'res_model': 'account.bank.statement.line',
            'res_id': self.statement_line_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def cron_process_due_flows(self):
        today = fields.Date.context_today(self)
        enabled_company_ids = self.env['res.company'].sudo().search([('prs_money_flow_enabled', '=', True)]).ids
        if not enabled_company_ids:
            return True
        base_domain = [
            ('company_id', 'in', enabled_company_ids),
            ('expected_date', '<=', today),
            ('projection_only', '=', False),
            ('statement_line_id', '=', False),
        ]
        # 1. Marcar como vencidos TODOS los flujos proyectados que llegaron a su fecha,
        #    independientemente de auto_create_statement: así el wizard los captura.
        planned = self.search(base_domain + [('state', '=', 'planned')])
        if planned:
            planned.write({'state': 'due'})
        # 2. Solo crear extractos para los flujos con creación automática habilitada.
        auto_flows = self.search(base_domain + [
            ('state', 'in', ('due', 'waiting_accreditation', 'manual_review')),
            ('auto_create_statement', '=', True),
        ])
        if auto_flows:
            auto_flows.action_create_statement_line()
        return True



    @api.model
    def _prs_cleanup_legacy_money_flow_actions(self):
        """Recover databases upgraded from intermediate PRS versions.

        Older builds created actions on technical SQL models
        ``prs.money.flow.calendar.event`` and ``prs.money.flow.grid.line``. If a
        browser reopens one of those stale action ids after the models were
        removed from the active UI, Odoo can answer with a plain Internal Server
        Error.  Keep the models registered for compatibility and also redirect
        those legacy actions/menus to the single supported action on
        ``prs.money.flow``.
        """
        safe_action = self.env.ref('payment_register_statement_v19.action_prs_money_flow', raise_if_not_found=False)
        safe_search = self.env.ref('payment_register_statement_v19.view_prs_money_flow_search', raise_if_not_found=False)
        safe_list = self.env.ref('payment_register_statement_v19.view_prs_money_flow_list', raise_if_not_found=False)
        safe_pivot = self.env.ref('payment_register_statement_v19.view_prs_money_flow_pivot', raise_if_not_found=False)
        safe_calendar = self.env.ref('payment_register_statement_v19.view_prs_money_flow_calendar', raise_if_not_found=False)
        safe_graph = self.env.ref('payment_register_statement_v19.view_prs_money_flow_graph', raise_if_not_found=False)
        safe_form = self.env.ref('payment_register_statement_v19.view_prs_money_flow_form', raise_if_not_found=False)
        if not safe_action:
            return True

        legacy_action_xmlids = [
            'payment_register_statement_v19.action_prs_money_flow_calendar_grouped',
            'payment_register_statement_v19.action_prs_money_flow_grid',
        ]
        for xmlid in legacy_action_xmlids:
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if not action:
                continue
            vals = {
                'name': 'Flujo de Pagos',
                'res_model': 'prs.money.flow',
                'view_mode': 'list,pivot,calendar,graph,form',
                'view_id': False,
                'context': "{'pivot_measures': ['amount_signed']}",
                'domain': '[]',
            }
            if safe_search and 'search_view_id' in action._fields:
                vals['search_view_id'] = safe_search.id
            action.sudo().write(vals)
            # Remove stale fixed view lines that point to the old SQL models.
            try:
                if 'view_ids' in action._fields and action.view_ids:
                    action.view_ids.unlink()
            except Exception:
                pass
            # Recreate deterministic action views for the supported model.
            try:
                ActionView = self.env['ir.actions.act_window.view'].sudo()
                sequence = 1
                for view, view_mode in (
                    (safe_list, 'list'),
                    (safe_pivot, 'pivot'),
                    (safe_calendar, 'calendar'),
                    (safe_graph, 'graph'),
                    (safe_form, 'form'),
                ):
                    if view:
                        ActionView.create({
                            'sequence': sequence,
                            'view_mode': view_mode,
                            'view_id': view.id,
                            'act_window_id': action.id,
                        })
                        sequence += 1
            except Exception:
                pass

        root_menu = self.env.ref('payment_register_statement_v19.menu_prs_money_flow_root', raise_if_not_found=False)
        if root_menu:
            # Keep the menu visible in the Accounting app and clear the technical
            # activation group that existed in intermediate builds.
            target = (
                self.env.ref('accountant.menu_accounting', raise_if_not_found=False)
                or self.env.ref('account.menu_finance', raise_if_not_found=False)
            )
            if not target:
                entries_menu = self.env.ref('account.menu_finance_entries', raise_if_not_found=False)
                target = entries_menu.parent_id if entries_menu and entries_menu.parent_id else False
            vals = {
                'active': True,
                'action': 'ir.actions.act_window,%s' % safe_action.id,
                'name': 'Flujo de Pagos',
                'group_ids': [(5, 0, 0)],
            }
            if target:
                vals['parent_id'] = target.id
            root_menu.sudo().write(vals)
        for xmlid in (
            'payment_register_statement_v19.menu_prs_money_flow',
            'payment_register_statement_v19.menu_prs_money_flow_calendar_grouped',
            'payment_register_statement_v19.menu_prs_money_flow_grid',
        ):
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                menu.sudo().write({'active': False})
        return True

    def _cron_sync_reconciled_state(self):
        reconciled = self.search([
            ('state', '=', 'statement_created'),
            ('statement_line_id', '!=', False),
        ]).filtered(lambda f: getattr(f.statement_line_id, 'is_reconciled', False))
        reconciled.write({'state': 'reconciled'})
        return True
