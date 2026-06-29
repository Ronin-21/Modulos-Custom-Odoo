# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

PAID_STATES = ('paid',)


class AccountMove(models.Model):
    _inherit = 'account.move'

    is_commissionable = fields.Boolean(
        string='Es comisionable',
        compute='_compute_is_commissionable',
        store=True,
        help='True si la factura proviene de una orden de venta con vendedor y la compañía tiene el módulo activo.',
    )
    commission_salesperson_id = fields.Many2one(
        'res.users',
        string='Vendedor de comisión',
        compute='_compute_commission_salesperson',
        store=True,
    )
    commission_sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de venta origen',
        compute='_compute_commission_sale_order',
        store=True,
    )
    commission_state = fields.Selection([
        ('not_commissionable', 'No comisionable'),
        ('pending_payment', 'Pendiente de pago'),
        ('earned', 'Comisión ganada'),
        ('settled', 'Confirmada'),
        ('paid', 'Pagada'),
        ('adjusted', 'Ajustada'),
        ('cancelled', 'Cancelada'),
    ], string='Estado comisión', default='not_commissionable',
        compute='_compute_commission_state', store=True)

    effective_payment_date = fields.Date(
        string='Fecha de pago efectivo',
        readonly=True,
        copy=False,
        help='Fecha en que la factura quedó completamente pagada.',
    )
    commission_line_ids = fields.One2many(
        'sale.commission.line',
        'move_id',
        string='Comisiones',
    )
    commission_count = fields.Integer(
        string='Comisiones',
        compute='_compute_commission_count',
    )

    @api.depends('move_type', 'invoice_line_ids.sale_line_ids')
    def _compute_is_commissionable(self):
        config_env = self.env['sale.commission.config']
        for move in self:
            if move.move_type != 'out_invoice':
                move.is_commissionable = False
                continue
            config = config_env.get_config(move.company_id)
            if not config.active:
                move.is_commissionable = False
                continue
            move.is_commissionable = bool(move._get_origin_sale_order())

    @api.depends('invoice_line_ids.sale_line_ids.order_id.user_id')
    def _compute_commission_salesperson(self):
        for move in self:
            order = move._get_origin_sale_order()
            move.commission_salesperson_id = order.user_id if order else False

    @api.depends('invoice_line_ids.sale_line_ids.order_id')
    def _compute_commission_sale_order(self):
        for move in self:
            order = move._get_origin_sale_order()
            move.commission_sale_order_id = order if order else False

    @api.depends('commission_line_ids.state', 'is_commissionable', 'payment_state', 'state')
    def _compute_commission_state(self):
        for move in self:
            if not move.is_commissionable or move.move_type != 'out_invoice':
                move.commission_state = 'not_commissionable'
                continue

            lines = move.commission_line_ids.filtered(lambda l: l.active and l.state != 'cancelled')
            if not lines:
                move.commission_state = 'pending_payment'
            elif all(l.state == 'paid' for l in lines):
                move.commission_state = 'paid'
            elif all(l.state in ('settled', 'paid') for l in lines):
                move.commission_state = 'settled'
            elif any(l.state == 'earned' for l in lines):
                move.commission_state = 'earned'
            elif any(l.state == 'adjusted' for l in lines):
                move.commission_state = 'adjusted'
            elif any(l.state == 'cancelled' for l in lines):
                move.commission_state = 'cancelled'
            else:
                move.commission_state = 'pending_payment'

    def _compute_commission_count(self):
        for move in self:
            move.commission_count = len(move.commission_line_ids.filtered(lambda l: l.active))

    def _get_origin_sale_order(self):
        self.ensure_one()
        orders = self.invoice_line_ids.sale_line_ids.order_id
        orders_with_seller = orders.filtered(lambda o: o.user_id)
        return orders_with_seller[:1] if orders_with_seller else orders[:1]

    def _get_effective_payment_date(self):
        self.ensure_one()
        reconcile_lines = self.line_ids.filtered(
            lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable') and l.reconciled
        )
        dates = (
            reconcile_lines.mapped('matched_credit_ids.credit_move_id.date')
            + reconcile_lines.mapped('matched_debit_ids.debit_move_id.date')
        )
        dates = [d for d in dates if d]
        return max(dates) if dates else fields.Date.today()

    def _is_after_commission_start_date(self, config, payment_date=None):
        self.ensure_one()
        start_date = config.commission_start_date
        compare_date = payment_date or self.invoice_date or self.date
        if not start_date or not compare_date:
            return True
        return compare_date >= start_date

    # ------------------------------------------------------------------
    # NUEVO FLUJO: draft al confirmar factura → earned al pagar
    # ------------------------------------------------------------------

    def _post(self, soft=True):
        """
        Hook en la confirmación de la factura.
        Crea la comisión en estado DRAFT ('Pendiente de pago') para que
        sea visible desde el momento en que se emite la factura, antes
        de que sea cobrada.
        """
        result = super()._post(soft=soft)
        for move in self:
            if move.move_type != 'out_invoice':
                continue
            if not move.is_commissionable:
                continue
            config = self.env['sale.commission.config'].get_config(move.company_id)
            if not config.active:
                continue
            if not self._is_after_commission_start_date(config):
                continue
            move._create_draft_commission()
        return result

    def _create_draft_commission(self):
        """
        Crea la comisión en estado DRAFT al confirmar la factura.
        Si ya existe una comisión activa no cancelada, no hace nada.
        """
        self.ensure_one()
        CommissionLine = self.env['sale.commission.line']

        existing = CommissionLine.search([
            ('move_id', '=', self.id),
            ('active', '=', True),
            ('state', 'not in', ('cancelled',)),
        ], limit=1)
        if existing:
            _logger.info('Comisión ya existente para factura %s. Omitiendo creación draft.', self.name)
            return

        salesperson = self.commission_salesperson_id
        if not salesperson:
            _logger.warning('Factura %s: sin vendedor. No se crea comisión draft.', self.name)
            return

        config = self.env['sale.commission.config'].get_config(self.company_id)
        sale_order = self.commission_sale_order_id
        base_amount = CommissionLine._get_base_amount(self, config)
        percent = CommissionLine._get_commission_percent(salesperson, self.company_id)
        commission_amount = CommissionLine._round_commission(base_amount * percent / 100.0, config)

        vals = {
            'salesperson_id': salesperson.id,
            'partner_id': self.partner_id.id,
            'sale_order_id': sale_order.id if sale_order else False,
            'move_id': self.id,
            'company_id': self.company_id.id,
            'commission_base_amount': base_amount,
            'commission_percent': percent,
            'commission_amount': commission_amount,
            'paid_amount_considered': 0.0,
            'payment_date': self.invoice_date or fields.Date.today(),
            'state': 'draft',  # Pendiente de pago
        }
        line = CommissionLine.create(vals)
        _logger.info(
            'Comisión DRAFT %s creada para factura %s, vendedor %s, importe estimado %s',
            line.name, self.name, salesperson.name, commission_amount
        )

    def _mark_commission_earned(self):
        """
        Mueve la comisión de DRAFT a EARNED cuando la factura queda pagada.
        Actualiza también la fecha de pago efectivo y el importe cobrado.
        """
        self.ensure_one()
        CommissionLine = self.env['sale.commission.line']

        draft_commission = CommissionLine.search([
            ('move_id', '=', self.id),
            ('active', '=', True),
            ('state', '=', 'draft'),
        ], limit=1)

        payment_date = self._get_effective_payment_date()

        if draft_commission:
            # Actualiza fecha real de pago y marca como ganada
            draft_commission.write({
                'state': 'earned',
                'payment_date': payment_date,
                'paid_amount_considered': draft_commission.commission_base_amount,
            })
            self.effective_payment_date = payment_date
            _logger.info(
                'Comisión %s marcada como EARNED para factura %s (pago: %s)',
                draft_commission.name, self.name, payment_date
            )
        else:
            # Fallback: si por alguna razón no existe el draft, crear directamente en earned
            _logger.warning(
                'Factura %s: no se encontró comisión draft. Creando directamente en earned.',
                self.name
            )
            self._generate_commission_earned(payment_date)

    def _generate_commission_earned(self, payment_date=None):
        """
        Crea una comisión directamente en estado EARNED.
        Se usa como fallback cuando no existe el draft previo.
        """
        self.ensure_one()
        CommissionLine = self.env['sale.commission.line']

        existing = CommissionLine.search([
            ('move_id', '=', self.id),
            ('active', '=', True),
            ('state', 'not in', ('cancelled',)),
        ], limit=1)
        if existing:
            return

        config = self.env['sale.commission.config'].get_config(self.company_id)
        if not config.active:
            return

        payment_date = payment_date or self._get_effective_payment_date()
        if not self._is_after_commission_start_date(config, payment_date=payment_date):
            return

        salesperson = self.commission_salesperson_id
        if not salesperson:
            return

        sale_order = self.commission_sale_order_id
        base_amount = CommissionLine._get_base_amount(self, config)
        percent = CommissionLine._get_commission_percent(salesperson, self.company_id)
        commission_amount = CommissionLine._round_commission(base_amount * percent / 100.0, config)

        vals = {
            'salesperson_id': salesperson.id,
            'partner_id': self.partner_id.id,
            'sale_order_id': sale_order.id if sale_order else False,
            'move_id': self.id,
            'company_id': self.company_id.id,
            'commission_base_amount': base_amount,
            'commission_percent': percent,
            'commission_amount': commission_amount,
            'paid_amount_considered': base_amount,
            'payment_date': payment_date,
            'state': 'earned',
        }
        line = CommissionLine.create(vals)
        self.effective_payment_date = payment_date
        _logger.info('Comisión EARNED (fallback) %s creada para factura %s', line.name, self.name)

    def _cancel_pending_commissions(self):
        """Cancela comisiones en draft/earned cuando se revierte el pago o la factura."""
        self.ensure_one()
        lines = self.commission_line_ids.filtered(
            lambda l: l.state not in ('paid', 'cancelled', 'settled')
        )
        lines.write({'state': 'cancelled'})
        self.effective_payment_date = False
        if lines:
            _logger.info('Comisiones canceladas en factura %s', self.name)

    def button_draft(self):
        """Al restablecer a borrador, cancela las comisiones pendientes."""
        res = super().button_draft()
        for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
            move._cancel_pending_commissions()
        return res

    def action_force_commission_check(self):
        self.ensure_one()
        # Si la factura está pagada y la comisión está en draft, marcarla como earned
        self.invalidate_recordset(['payment_state'])
        if self.payment_state in PAID_STATES:
            draft = self.commission_line_ids.filtered(
                lambda l: l.active and l.state == 'draft'
            )
            if draft:
                self._mark_commission_earned()
            elif not self.commission_line_ids.filtered(
                lambda l: l.active and l.state not in ('cancelled',)
            ):
                self._generate_commission_earned()
        elif self.is_commissionable and self.state == 'posted':
            # Factura posted pero sin comisión draft → crearla
            if not self.commission_line_ids.filtered(
                lambda l: l.active and l.state not in ('cancelled',)
            ):
                self._create_draft_commission()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Comisión verificada',
                'message': 'Se verificó el estado de comisión para esta factura.',
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def _cron_generate_missing_commissions(self):
        """
        Cron de seguridad:
        1. Facturas posted sin comisión draft → crea el draft.
        2. Facturas pagadas con comisión en draft → marca como earned.
        3. Facturas pagadas sin ninguna comisión → crea directamente en earned.
        """
        companies = self.env['res.company'].search([])
        for company in companies:
            config = self.env['sale.commission.config'].get_config(company)
            if not config.active:
                continue

            base_domain = [
                ('company_id', '=', company.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('is_commissionable', '=', True),
            ]

            # Paso 1: Facturas posted sin comisión → crear draft
            posted_moves = self.search(base_domain)
            for move in posted_moves:
                has_commission = self.env['sale.commission.line'].search_count([
                    ('move_id', '=', move.id),
                    ('active', '=', True),
                    ('state', 'not in', ('cancelled',)),
                ])
                if not has_commission:
                    try:
                        move._create_draft_commission()
                        _logger.info('Cron: draft creado para factura %s', move.name)
                    except Exception as e:
                        _logger.error('Cron: error en draft de factura %s: %s', move.name, str(e))

            # Paso 2: Facturas pagadas con draft → marcar earned
            paid_moves = self.search(base_domain + [('payment_state', 'in', PAID_STATES)])
            for move in paid_moves:
                draft = self.env['sale.commission.line'].search([
                    ('move_id', '=', move.id),
                    ('active', '=', True),
                    ('state', '=', 'draft'),
                ], limit=1)
                if draft:
                    try:
                        move._mark_commission_earned()
                        _logger.info('Cron: comisión earned para factura %s', move.name)
                    except Exception as e:
                        _logger.error('Cron: error earned en factura %s: %s', move.name, str(e))

    def action_view_commissions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Comisiones',
            'res_model': 'sale.commission.line',
            'view_mode': 'list,form',
            'domain': [('move_id', '=', self.id)],
            'context': {'default_move_id': self.id},
        }

    def _reverse_moves(self, default_values_list=None, cancel=False):
        moves = super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)
        config = self.env['sale.commission.config'].get_config(self.env.company)
        for move in self:
            earned_lines = move.commission_line_ids.filtered(
                lambda l: l.state in ('earned', 'settled')
            )
            if not earned_lines:
                continue
            behavior = config.credit_note_behavior
            if behavior == 'auto_deduct':
                earned_lines.write({'state': 'adjusted'})
            elif behavior == 'block':
                earned_lines.write({'state': 'adjusted'})
                _logger.info(
                    'Comisiones bloqueadas por nota de crédito en factura %s. '
                    'Requieren revisión manual.', move.name
                )
            elif behavior == 'negative_adjustment':
                for line in earned_lines:
                    self.env['sale.commission.line'].create({
                        'salesperson_id': line.salesperson_id.id,
                        'partner_id': line.partner_id.id,
                        'sale_order_id': line.sale_order_id.id if line.sale_order_id else False,
                        'move_id': line.move_id.id,
                        'company_id': line.company_id.id,
                        'commission_base_amount': -line.commission_base_amount,
                        'commission_percent': line.commission_percent,
                        'commission_amount': -line.commission_amount,
                        'paid_amount_considered': -line.paid_amount_considered,
                        'payment_date': fields.Date.today(),
                        'state': 'earned',
                        'notes': f'Ajuste negativo por nota de crédito sobre {line.name}',
                    })
                    line.write({'state': 'adjusted'})
        return moves


class AccountPartialReconcile(models.Model):
    """
    Hook en la conciliación parcial: cuando una factura queda completamente
    pagada, mueve la comisión de DRAFT a EARNED.
    """
    _inherit = 'account.partial.reconcile'

    @api.model_create_multi
    def create(self, vals_list):
        result = super().create(vals_list)
        self._check_commissions_after_reconcile(result)
        return result

    def unlink(self):
        moves_to_check = (
            self.mapped('debit_move_id.move_id') |
            self.mapped('credit_move_id.move_id')
        ).filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted')
        result = super().unlink()
        for move in moves_to_check:
            try:
                move.invalidate_recordset(['payment_state'])
                if move.payment_state not in PAID_STATES:
                    # Volvió a unpaid: revertir earned a draft
                    earned = move.commission_line_ids.filtered(
                        lambda l: l.active and l.state == 'earned'
                    )
                    if earned:
                        earned.write({
                            'state': 'draft',
                            'paid_amount_considered': 0.0,
                        })
                        move.effective_payment_date = False
                        _logger.info(
                            'Comisión revertida a DRAFT por desconciliación en factura %s',
                            move.name
                        )
            except Exception as e:
                _logger.error(
                    'Error al revertir comisión por desconciliación en factura %s: %s',
                    move.name, str(e)
                )
        return result

    @api.model
    def _check_commissions_after_reconcile(self, reconciles):
        candidate_moves = (
            reconciles.mapped('debit_move_id.move_id') |
            reconciles.mapped('credit_move_id.move_id')
        ).filtered(
            lambda m: m.move_type == 'out_invoice'
            and m.state == 'posted'
            and m.is_commissionable
        )

        for move in candidate_moves:
            try:
                move.invalidate_recordset(['payment_state'])
                if move.payment_state not in PAID_STATES:
                    continue
                # Buscar comisión draft para marcar como earned
                draft = move.commission_line_ids.filtered(
                    lambda l: l.active and l.state == 'draft'
                )
                if draft:
                    move._mark_commission_earned()
                elif not move.commission_line_ids.filtered(
                    lambda l: l.active and l.state not in ('cancelled',)
                ):
                    # Fallback: no hay draft, crear directo en earned
                    move._generate_commission_earned()
                _logger.info(
                    'Comisión procesada vía conciliación para factura %s', move.name
                )
            except Exception as e:
                _logger.error(
                    'Error procesando comisión post-conciliación para factura %s: %s',
                    move.name, str(e)
                )
