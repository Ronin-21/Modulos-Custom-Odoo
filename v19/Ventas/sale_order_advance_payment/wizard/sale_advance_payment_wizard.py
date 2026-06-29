import logging
from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError

from .sale_advance_payment_line import _CHECK_PAYMENT_METHOD_CODES

_logger = logging.getLogger(__name__)


class SaleAdvancePaymentWizard(models.TransientModel):
    _name = 'sale.advance.payment.wizard'
    _description = 'Wizard de Registro de Pago Adelantado en Orden de Venta'

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de Venta',
        required=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        readonly=True,
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        readonly=True,
        required=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        readonly=True,
        required=True,
    )
    payment_date = fields.Date(
        string='Fecha de Pago',
        required=True,
        default=fields.Date.today,
    )
    reference = fields.Char(
        string='Referencia',
        help='Referencia interna del pago (número de comprobante bancario, etc.)',
    )
    note = fields.Text(string='Notas Internas')

    # ── Configuración (desde res.company) ─────────────────────────────────────
    allowed_journal_ids = fields.Many2many(
        'account.journal',
        string='Diarios Permitidos',
        compute='_compute_allowed_journal_ids',
    )
    require_reference = fields.Boolean(
        related='company_id.sale_advance_payment_require_reference',
        string='Requiere Referencia',
    )

    payment_mode = fields.Selection(
        selection=[
            ('single', 'Pago único'),
            ('multi', 'Múltiples métodos'),
        ],
        string='Modo de cobro',
        default='single',
        required=True,
    )

    # ── Modo único ────────────────────────────────────────────────────────────
    amount = fields.Monetary(
        string='Importe a Recibir',
        currency_field='currency_id',
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario',
        domain="[('id', 'in', allowed_journal_ids)]",
    )
    payment_method_line_id = fields.Many2one(
        'account.payment.method.line',
        string='Método de Pago',
        domain="[('journal_id', '=', journal_id), ('payment_type', '=', 'inbound')]",
    )
    single_is_check = fields.Boolean(
        string='Pago único con cheque',
        compute='_compute_payment_flags',
    )

    # ── Modo múltiple ─────────────────────────────────────────────────────────
    line_ids = fields.One2many(
        'sale.advance.payment.line',
        'wizard_id',
        string='Líneas de pago',
    )
    multi_total = fields.Monetary(
        string='Total ingresado',
        currency_field='currency_id',
        compute='_compute_multi_totals',
    )
    multi_difference = fields.Monetary(
        string='Diferencia con el total',
        currency_field='currency_id',
        compute='_compute_multi_totals',
    )
    multi_has_check = fields.Boolean(
        string='Múltiple con cheque',
        compute='_compute_payment_flags',
    )

    # ── Cheques ───────────────────────────────────────────────────────────────
    check_ids = fields.One2many(
        'sale.advance.payment.check',
        'wizard_id',
        string='Cheques',
    )
    check_total = fields.Monetary(
        string='Total cheques',
        currency_field='currency_id',
        compute='_compute_check_total',
    )
    checks_available = fields.Boolean(
        string='Cheques disponibles',
        compute='_compute_checks_available',
        help='True si la localización de cheques (l10n_latam_check) está instalada.',
    )
    show_checks_tab = fields.Boolean(
        string='Mostrar pestaña Cheques',
        compute='_compute_payment_flags',
    )

    # ── Informativos ──────────────────────────────────────────────────────────
    sale_order_amount_total = fields.Monetary(
        string='Total Orden de Venta',
        currency_field='currency_id',
        readonly=True,
    )

    # =========================================================================
    # COMPUTE
    # =========================================================================
    @api.depends('company_id')
    def _compute_allowed_journal_ids(self):
        Journal = self.env['account.journal']
        for wizard in self:
            configured = wizard.company_id.sale_advance_payment_journal_ids
            if configured:
                wizard.allowed_journal_ids = configured
            else:
                wizard.allowed_journal_ids = Journal.search([
                    ('type', 'in', ['bank', 'cash']),
                    ('company_id', '=', wizard.company_id.id),
                ])

    @api.depends_context('uid')
    def _compute_checks_available(self):
        # Duck-typing: la pestaña de cheques solo aplica si l10n_latam_check
        # agregó el campo de cheques nuevos a account.payment.
        available = 'l10n_latam_new_check_ids' in self.env['account.payment']._fields
        for wizard in self:
            wizard.checks_available = available

    @api.depends(
        'payment_mode',
        'payment_method_line_id', 'payment_method_line_id.code',
        'line_ids.is_check',
        'checks_available',
    )
    def _compute_payment_flags(self):
        for wizard in self:
            single_check = bool(
                wizard.payment_mode == 'single'
                and (wizard.payment_method_line_id.code or '') in _CHECK_PAYMENT_METHOD_CODES
            )
            multi_check = bool(
                wizard.payment_mode == 'multi'
                and any(line.is_check for line in wizard.line_ids)
            )
            wizard.single_is_check = single_check
            wizard.multi_has_check = multi_check
            wizard.show_checks_tab = wizard.checks_available and (single_check or multi_check)

    @api.depends('check_ids.amount')
    def _compute_check_total(self):
        for wizard in self:
            wizard.check_total = sum(wizard.check_ids.mapped('amount'))

    @api.depends('line_ids.amount', 'sale_order_amount_total')
    def _compute_multi_totals(self):
        for wizard in self:
            total = sum(wizard.line_ids.mapped('amount'))
            wizard.multi_total = total
            wizard.multi_difference = wizard.sale_order_amount_total - total

    # =========================================================================
    # DEFAULTS / ONCHANGE
    # =========================================================================
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('default_sale_order_id') or self.env.context.get('active_id')
        if active_id:
            sale_order = self.env['sale.order'].browse(active_id)
            company = sale_order.company_id
            # Saldo restante = total - anticipos ya registrados (para múltiples anticipos)
            remaining = sale_order.amount_total - sale_order.advance_payment_amount
            if remaining < 0:
                remaining = 0.0
            res.update({
                'sale_order_id': sale_order.id,
                'partner_id': (sale_order.partner_invoice_id or sale_order.partner_id).id,
                'company_id': company.id,
                'currency_id': sale_order.currency_id.id,
                'amount': remaining,
                'sale_order_amount_total': sale_order.amount_total,
                'payment_mode': company.sale_advance_payment_default_mode or 'single',
            })
            # Diario por defecto (si está configurado y es de banco/efectivo de la empresa)
            default_journal = company.sale_advance_payment_default_journal_id
            if (
                default_journal
                and default_journal.type in ('bank', 'cash')
                and default_journal.company_id == company
            ):
                res['journal_id'] = default_journal.id
                available = default_journal._get_available_payment_method_lines('inbound')
                non_check = available.filtered(lambda m: m.code not in _CHECK_PAYMENT_METHOD_CODES)
                method = non_check[:1] or available[:1]
                if method:
                    res['payment_method_line_id'] = method.id
        return res

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        self.payment_method_line_id = False
        if self.journal_id:
            available = self.journal_id._get_available_payment_method_lines('inbound')
            non_check = available.filtered(lambda m: m.code not in _CHECK_PAYMENT_METHOD_CODES)
            self.payment_method_line_id = non_check[:1] or available[:1]

    @api.onchange('payment_mode')
    def _onchange_payment_mode(self):
        if self.payment_mode == 'multi':
            # Sembrar una línea a partir de los datos del modo único.
            if not self.line_ids and self.journal_id:
                self.line_ids = [Command.create({
                    'journal_id': self.journal_id.id,
                    'payment_method_line_id': self.payment_method_line_id.id or False,
                    'amount': self.amount or self.sale_order_amount_total,
                    'communication': self.reference or False,
                })]
        else:
            # Volver a único: limpiar líneas múltiples.
            self.line_ids = [Command.clear()]

    @api.onchange('single_is_check', 'multi_has_check')
    def _onchange_reset_checks(self):
        # Si ya no hay método de cheque seleccionado, limpiar los cheques cargados.
        if not self.single_is_check and not self.multi_has_check:
            self.check_ids = [Command.clear()]

    @api.onchange('check_total', 'single_is_check')
    def _onchange_sync_single_check_amount(self):
        if self.payment_mode != 'single':
            return
        if self.single_is_check:
            # Con cheque, el importe lo determinan los cheques.
            self.amount = self.check_total
        elif not self.amount or self.amount <= 0:
            # Al salir del modo cheque, restaurar el importe al total de la orden.
            self.amount = self.sale_order_amount_total

    @api.onchange('check_total', 'multi_has_check')
    def _onchange_sync_multi_check_amount(self):
        # En modo múltiple, la línea de cheque toma el total de los cheques.
        if self.payment_mode == 'multi' and self.multi_has_check:
            check_lines = self.line_ids.filtered('is_check')
            if len(check_lines) == 1:
                check_lines.amount = self.check_total

    # =========================================================================
    # VALIDACIÓN
    # =========================================================================
    def _remaining_amount(self):
        """Saldo de la orden aún no cubierto por anticipos activos."""
        self.ensure_one()
        remaining = self.sale_order_id.amount_total - self.sale_order_id.advance_payment_amount
        return remaining if remaining > 0 else 0.0

    def _validate_common(self):
        self.ensure_one()
        sale_order = self.sale_order_id

        if sale_order.state != 'sale':
            raise UserError(_(
                'La Orden de Venta debe estar confirmada (estado "En Proceso de Venta") '
                'para registrar un pago adelantado.'
            ))

        if (
            not self.company_id.sale_advance_payment_allow_multiple
            and sale_order.advance_payment_count > 0
        ):
            raise UserError(_(
                'Esta orden ya tiene un pago adelantado registrado. '
                'Para permitir varios, activá "Permitir Múltiples Anticipos" en Ajustes.'
            ))

        if self.require_reference and not self.reference:
            raise UserError(_('Debe ingresar una Referencia para registrar el pago.'))

    def _validate_checks(self, check_lines_count):
        """Valida la coherencia de los cheques cargados."""
        self.ensure_one()
        if not self.check_ids:
            return
        if not self.checks_available:
            raise UserError(_(
                'No se puede registrar un pago con cheques: la localización de cheques '
                '(l10n_latam_check) no está instalada en esta base.'
            ))
        if check_lines_count > 1:
            raise UserError(_(
                'Por ahora solo se admite una línea de cheque por pago adelantado. '
                'Cargá todos los cheques bajo un único método de cheque.'
            ))
        if any(c.amount <= 0 for c in self.check_ids):
            raise UserError(_('El importe de cada cheque debe ser mayor a cero.'))

    def _validate_single(self):
        self.ensure_one()
        sale_order = self.sale_order_id

        if self.single_is_check:
            if not self.check_ids:
                raise UserError(_('Agregá los cheques en la pestaña "Cheques" antes de registrar el pago.'))
            self.amount = self.check_total
            self._validate_checks(1 if self.single_is_check else 0)

        if self.amount <= 0:
            raise UserError(_('El importe debe ser mayor a cero.'))
        remaining = self._remaining_amount()
        if self.amount > remaining:
            raise UserError(_(
                'El pago adelantado no puede superar el saldo pendiente de la Orden de Venta.\n'
                'Saldo pendiente: %s\nImporte ingresado: %s'
            ) % (remaining, self.amount))
        if not self.journal_id:
            raise UserError(_('Debe seleccionar un diario de pago.'))
        if self.journal_id.company_id != self.company_id:
            raise UserError(_(
                'El diario "%s" no pertenece a la empresa "%s".'
            ) % (self.journal_id.name, self.company_id.name))

    def _validate_multi(self):
        self.ensure_one()
        sale_order = self.sale_order_id

        effective_lines = self.line_ids.filtered(lambda l: l.journal_id)
        if not effective_lines:
            raise UserError(_('Agregá al menos una línea de pago.'))

        # Sincronizar el importe de la línea de cheque con el total de cheques.
        check_lines = effective_lines.filtered('is_check')
        if check_lines:
            if len(check_lines) > 1:
                raise UserError(_(
                    'Por ahora solo se admite una línea de cheque en el cobro múltiple.'
                ))
            if not self.check_ids:
                raise UserError(_('Agregá los cheques en la pestaña "Cheques" para la línea de cheque.'))
            check_lines.amount = self.check_total
            self._validate_checks(len(check_lines))

        if any(line.amount <= 0 for line in effective_lines):
            raise UserError(_('El importe de cada línea de pago debe ser mayor a cero.'))

        total = sum(effective_lines.mapped('amount'))
        if total <= 0:
            raise UserError(_('El total a recibir debe ser mayor a cero.'))
        remaining = self._remaining_amount()
        if total > remaining:
            raise UserError(_(
                'El total de los pagos no puede superar el saldo pendiente de la Orden de Venta.\n'
                'Saldo pendiente: %s\nTotal ingresado: %s'
            ) % (remaining, total))

        for line in effective_lines:
            if line.journal_id.company_id != self.company_id:
                raise UserError(_(
                    'El diario "%s" no pertenece a la empresa "%s".'
                ) % (line.journal_id.name, self.company_id.name))

    # =========================================================================
    # CREACIÓN DE PAGOS
    # =========================================================================
    def _prepare_payment_vals(self, journal, method_line, amount, communication):
        self.ensure_one()
        memo = communication or self.reference or _('Pago adelantado - %s') % self.sale_order_id.name
        vals = {
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'amount': amount,
            'date': self.payment_date,
            'journal_id': journal.id,
            'memo': memo,
            'sale_order_id': self.sale_order_id.id,
        }
        if method_line:
            vals['payment_method_line_id'] = method_line.id
        return vals

    def _attach_checks(self, vals):
        """Adjunta los cheques cargados al pago (solo si l10n_latam_check está)."""
        self.ensure_one()
        if not self.checks_available or not self.check_ids:
            return vals
        vals['l10n_latam_new_check_ids'] = [Command.create({
            'name': check.name,
            'bank_id': check.bank_id.id if check.bank_id else False,
            'issuer_vat': check.issuer_vat or False,
            'payment_date': check.payment_date,
            'amount': check.amount,
        }) for check in self.check_ids]
        # El importe del pago lo determinan los cheques.
        vals['amount'] = sum(self.check_ids.mapped('amount'))
        return vals

    def _create_payments(self):
        """Crea y postea los account.payment. Devuelve el recordset de pagos."""
        self.ensure_one()
        Payment = self.env['account.payment']
        payment_vals_list = []

        if self.payment_mode == 'single':
            vals = self._prepare_payment_vals(
                self.journal_id, self.payment_method_line_id, self.amount, self.reference,
            )
            if self.single_is_check:
                vals = self._attach_checks(vals)
            payment_vals_list.append(vals)
        else:
            for line in self.line_ids.filtered(lambda l: l.journal_id and l.amount > 0):
                vals = self._prepare_payment_vals(
                    line.journal_id, line.payment_method_line_id, line.amount, line.communication,
                )
                if line.is_check:
                    vals = self._attach_checks(vals)
                payment_vals_list.append(vals)

        payments = Payment.create(payment_vals_list)
        payments.action_post()
        return payments

    def action_confirm(self):
        self.ensure_one()
        self._validate_common()

        if self.payment_mode == 'single':
            self._validate_single()
        else:
            self._validate_multi()

        sale_order = self.sale_order_id
        payments = self._create_payments()
        total_amount = sum(payments.mapped('amount'))

        # Diario/método representativos (el primer pago) para la ficha de trazabilidad.
        primary = payments[:1]

        # Número correlativo del anticipo dentro de la orden (-01, -02, ...).
        existing = self.env['sale.order.advance.payment'].search_count([
            ('sale_order_id', '=', sale_order.id),
        ])
        advance_name = '%s-%02d' % (sale_order.name, existing + 1)
        advance = self.env['sale.order.advance.payment'].create({
            'name': advance_name,
            'sale_order_id': sale_order.id,
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'amount': total_amount,
            'payment_date': self.payment_date,
            'journal_id': primary.journal_id.id if primary else False,
            'payment_method_line_id': primary.payment_method_line_id.id if primary.payment_method_line_id else False,
            'payment_id': primary.id if primary else False,
            'state': 'posted',
            'reference': self.reference,
            'note': self.note,
        })

        # Vincular todos los pagos con la ficha de trazabilidad.
        payments.write({'sale_advance_payment_id': advance.id})
        sale_order.write({'advance_payment_id': advance.id})

        _logger.info(
            'Pago adelantado %s registrado para la Orden de Venta %s. Pagos: %s.',
            advance_name, sale_order.name, ', '.join(payments.mapped('name')),
        )

        return {
            'type': 'ir.actions.act_window',
            'name': _('Pago Adelantado Registrado'),
            'res_model': 'sale.order.advance.payment',
            'view_mode': 'form',
            'res_id': advance.id,
            'target': 'current',
        }
