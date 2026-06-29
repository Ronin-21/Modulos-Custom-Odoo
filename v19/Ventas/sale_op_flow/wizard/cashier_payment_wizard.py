# -*- coding: utf-8 -*-
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaleCashierPaymentWizard(models.TransientModel):
    _name = 'sale.cashier.payment.wizard'
    _description = 'Wizard de Cobro en Caja'

    sale_order_id = fields.Many2one('sale.order', string='Pedido', required=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', related='sale_order_id.partner_id', readonly=True)
    order_amount_untaxed = fields.Monetary(
        string='Subtotal', related='sale_order_id.amount_untaxed', readonly=True, currency_field='currency_id',
    )
    order_amount_total = fields.Monetary(
        string='Total pedido', related='sale_order_id.amount_total', readonly=True, currency_field='currency_id',
    )
    proposed_payment_journal_id = fields.Many2one(
        'account.journal', string='Medio sugerido por ventas',
        related='sale_order_id.proposed_payment_journal_id', readonly=True,
    )

    payment_mode = fields.Selection(
        [('single', 'Pago único'), ('multi', 'Múltiples pagos')],
        string='Modo de cobro',
        default='single',
        required=True,
    )

    # ── Líneas maestras (todas las líneas, usadas para procesar y calcular) ──
    payment_line_ids = fields.One2many(
        'sale.cashier.payment.line', 'wizard_id', string='Todos los medios',
    )

    # ── Líneas por tipo (para la vista seccional) ─────────────────────────
    cash_line_ids = fields.One2many(
        'sale.cashier.payment.line', 'wizard_id',
        domain=[('line_type', '=', 'cash')],
        string='Efectivo',
    )
    bank_line_ids = fields.One2many(
        'sale.cashier.payment.line', 'wizard_id',
        domain=[('line_type', '=', 'bank')],
        string='Banco / Transferencia',
    )
    check_line_ids = fields.One2many(
        'sale.cashier.payment.line', 'wizard_id',
        domain=[('line_type', '=', 'check')],
        string='Cheques',
    )
    cc_line_ids = fields.One2many(
        'sale.cashier.payment.line', 'wizard_id',
        domain=[('line_type', '=', 'cc')],
        string='Cuenta Corriente',
    )

    # ── Totales computados ────────────────────────────────────────────────────
    multi_total = fields.Monetary(
        string='Total ingresado', compute='_compute_multi_totals', currency_field='currency_id',
    )
    total_adjustment = fields.Monetary(
        string='Ajuste del plan', compute='_compute_multi_totals', currency_field='currency_id',
    )
    total_to_collect = fields.Monetary(
        string='Total a cobrar', compute='_compute_multi_totals', currency_field='currency_id',
    )
    multi_remaining = fields.Monetary(
        string='Diferencia', compute='_compute_multi_totals', currency_field='currency_id',
    )
    surcharge_amount = fields.Monetary(
        string='Recargo incluido', compute='_compute_multi_totals', currency_field='currency_id',
    )
    check_excess_amount = fields.Monetary(
        string='Crédito a favor del cliente', compute='_compute_multi_totals', currency_field='currency_id',
    )
    multi_is_balanced = fields.Boolean(compute='_compute_multi_totals')
    has_surcharge = fields.Boolean(compute='_compute_multi_totals')
    has_check_excess = fields.Boolean(compute='_compute_multi_totals')
    has_payment_line = fields.Boolean(compute='_compute_has_payment_line')
    has_pay_later = fields.Boolean(compute='_compute_has_pay_later')
    total_cash_change = fields.Monetary(
        string='Vuelto total', compute='_compute_cash_change_total', currency_field='currency_id',
    )
    has_cash_change = fields.Boolean(compute='_compute_cash_change_total')

    @api.depends('cash_line_ids', 'bank_line_ids', 'check_line_ids', 'cc_line_ids')
    def _compute_has_payment_line(self):
        for wiz in self:
            wiz.has_payment_line = bool(
                wiz.cash_line_ids or wiz.bank_line_ids or wiz.check_line_ids or wiz.cc_line_ids
            )

    @api.depends('cc_line_ids')
    def _compute_has_pay_later(self):
        for wiz in self:
            wiz.has_pay_later = bool(wiz.cc_line_ids)

    @api.depends('cash_line_ids.cash_received', 'cash_line_ids.amount')
    def _compute_cash_change_total(self):
        for wiz in self:
            change = sum(
                max((l.cash_received or 0.0) - (l.amount or 0.0), 0.0)
                for l in wiz.cash_line_ids
            )
            wiz.total_cash_change = round(change, 2) if change > 0.01 else 0.0
            wiz.has_cash_change = change > 0.01

    invoice_journal_id = fields.Many2one(
        'account.journal',
        string='Diario de facturación',
        domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]",
        help='Diario contable con el que se emitirá la factura.',
    )
    invoice_document_type_name = fields.Char(
        string='Tipo de comprobante',
        compute='_compute_invoice_document_type', readonly=True,
        help='Comprobante que emitirá AFIP según la responsabilidad del cliente '
             'y el diario electrónico seleccionado (ej. FACTURA A/B/C).',
    )
    show_invoice_document_type = fields.Boolean(compute='_compute_invoice_document_type')
    sof_invoice_preference = fields.Selection(
        related='sale_order_id.sof_invoice_preference', readonly=True,
        string='Comprobante solicitado',
    )
    cashier_session_id = fields.Many2one(
        'sale.cashier.session', string='Sesión de caja',
        compute='_compute_cashier_session', store=False, readonly=True,
    )
    session_info = fields.Char(string='Info sesión', compute='_compute_cashier_session', readonly=True)
    company_id = fields.Many2one('res.company', related='sale_order_id.company_id', store=False, readonly=True)
    currency_id = fields.Many2one('res.currency', related='sale_order_id.currency_id', store=False, readonly=True)

    @api.depends(
        'payment_mode',
        'cash_line_ids.amount', 'cash_line_ids.financing_plan_id',
        'bank_line_ids.amount', 'bank_line_ids.financing_plan_id',
        'check_line_ids.amount', 'check_line_ids.financing_plan_id',
        'cc_line_ids.amount', 'cc_line_ids.financing_plan_id',
        'sale_order_id.amount_total',
        'sale_order_id.amount_untaxed',
    )
    def _compute_multi_totals(self):
        try:
            rid = int(self.env['ir.config_parameter'].sudo().get_param(
                'sale_op_flow.cash_rounding_id', '0') or 0)
            cash_rounding = self.env['account.cash.rounding'].browse(rid) if rid else False
            if cash_rounding and not cash_rounding.exists():
                cash_rounding = False
        except (ValueError, TypeError):
            cash_rounding = False

        for wiz in self:
            # Usar la union de los campos tipados en lugar del master payment_line_ids.
            # En onchange, Odoo 19 solo actualiza los campos tipados (bank_line_ids, etc.)
            # sin sincronizar el master, por lo que payment_line_ids quedaria desactualizado.
            all_lines = wiz.cash_line_ids | wiz.bank_line_ids | wiz.check_line_ids | wiz.cc_line_ids
            multi_total = sum(all_lines.mapped('amount'))
            wiz.multi_total = multi_total
            order_total = wiz.order_amount_total

            if wiz.payment_mode == 'single':
                base = wiz.order_amount_untaxed
                adjustment = 0.0
                seen_plan_ids = set()
                for line in all_lines:
                    plan = line.financing_plan_id
                    if (plan and plan.id not in seen_plan_ids
                            and plan.adjustment_type != 'none' and plan.adjustment_rate):
                        seen_plan_ids.add(plan.id)
                        if plan.adjustment_type == 'discount':
                            adjustment -= base * plan.adjustment_rate / 100.0
                        else:
                            adjustment += base * plan.adjustment_rate / 100.0
                wiz.total_adjustment = adjustment
                total_to_collect = order_total + adjustment
                if cash_rounding:
                    total_to_collect = cash_rounding.round(total_to_collect)
                wiz.total_to_collect = total_to_collect
                wiz.multi_remaining = total_to_collect - multi_total
                wiz.surcharge_amount = 0.0
                wiz.check_excess_amount = 0.0
                wiz.multi_is_balanced = wiz.multi_remaining <= 0.01
                wiz.has_surcharge = False
                wiz.has_check_excess = False
            else:
                wiz.total_adjustment = 0.0
                # Calcular recargo de planes por separado del exceso de cheques
                plan_surcharge = 0.0
                for line in all_lines:
                    plan = line.financing_plan_id
                    if plan and plan.adjustment_type == 'surcharge' and plan.adjustment_rate and (line.amount or 0.0) > 0:
                        base_amt = round(line.amount / (1.0 + plan.adjustment_rate / 100.0), 2)
                        plan_surcharge += line.amount - base_amt
                plan_surcharge = round(plan_surcharge, 2)
                # El recargo se agrega a la factura, por lo que "falta asignar" es contra
                # (pedido + recargo), no contra el pedido solo.
                effective_invoice = order_total + plan_surcharge
                if cash_rounding:
                    effective_invoice = cash_rounding.round(effective_invoice)
                wiz.total_to_collect = effective_invoice
                wiz.multi_remaining = effective_invoice - multi_total
                surplus = multi_total - effective_invoice
                check_excess = round(surplus, 2) if surplus > 0.01 else 0.0
                wiz.surcharge_amount = plan_surcharge if plan_surcharge > 0.01 else 0.0
                wiz.check_excess_amount = check_excess if check_excess > 0.01 else 0.0
                wiz.has_surcharge = plan_surcharge > 0.01
                wiz.has_check_excess = check_excess > 0.01
                wiz.multi_is_balanced = wiz.multi_remaining <= 0.01

    def _get_available_cashier_session(self, company):
        """Busca una sesión abierta disponible para cobrar."""
        Session = self.env['sale.cashier.session'].sudo()
        ctx_session_id = (
            self.env.context.get('sof_cashier_session_id')
            or self.env.context.get('default_cashier_session_id')
        )
        if ctx_session_id:
            selected = Session.browse(ctx_session_id).exists()
            if selected and selected.state == 'open':
                return selected

        if company:
            session = Session.search([
                ('state', '=', 'open'),
                ('company_id', '=', company.id),
            ], limit=1)
            if session:
                return session

        return Session.search([('state', '=', 'open')], limit=1)

    @api.depends('sale_order_id')
    def _compute_cashier_session(self):
        for wiz in self:
            company = wiz.sale_order_id.company_id or self.env.company
            session = wiz._get_available_cashier_session(company)
            wiz.cashier_session_id = session
            wiz.session_info = session.name if session else _('Sin sesión abierta')

    @api.depends('invoice_journal_id', 'partner_id')
    def _compute_invoice_document_type(self):
        """Predice el comprobante (FACTURA A/B/C) que emitirá el diario electrónico
        según la responsabilidad AFIP del cliente, replicando el cómputo nativo de
        l10n_ar sobre una factura en memoria (sin persistir)."""
        Move = self.env['account.move']
        for wiz in self:
            name = False
            journal = wiz.invoice_journal_id
            partner = wiz.partner_id
            uses_docs = bool(journal) and 'l10n_latam_use_documents' in journal._fields \
                and journal.l10n_latam_use_documents
            if uses_docs and partner:
                try:
                    move = Move.new({
                        'move_type': 'out_invoice',
                        'journal_id': journal.id,
                        'partner_id': partner.id,
                        'company_id': (journal.company_id or wiz.company_id).id,
                    })
                    doc_type = move.l10n_latam_document_type_id
                    if doc_type:
                        name = doc_type.display_name
                except Exception:
                    name = False
            wiz.invoice_document_type_name = name
            wiz.show_invoice_document_type = bool(name)

    @api.onchange('payment_mode')
    def _onchange_payment_mode(self):
        # Al pasar a "Pago único" se cobra con un solo medio: hay que limpiar todas las
        # secciones. Las líneas se manejan por los campos tipados (cash/bank/check/cc), no
        # por el master payment_line_ids, así que hay que vaciar esos campos (vaciar solo el
        # master no borra las líneas en pantalla). El cajero vuelve a cargar el medio único.
        if self.payment_mode == 'single':
            self.cash_line_ids = [(5, 0, 0)]
            self.bank_line_ids = [(5, 0, 0)]
            self.check_line_ids = [(5, 0, 0)]
            self.cc_line_ids = [(5, 0, 0)]
            self.payment_line_ids = [(5, 0, 0)]

    @api.model
    def _create_for_order(self, order):
        """Crea el wizard server-side para que los computed fields (totales, has_payment_line)
        funcionen correctamente al abrir el formulario en Odoo 19 OWL.
        Debe llamarse con el contexto correcto ya aplicado (default_sale_order_id, sof_cashier_session_id).
        """
        # Solo los campos que default_get necesita procesar; no incluir computados ni readonly.
        fields_list = ['sale_order_id', 'payment_line_ids', 'invoice_journal_id', 'payment_mode']
        vals = self.default_get(fields_list)
        vals['sale_order_id'] = order.id
        return self.create(vals)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order_id = res.get('sale_order_id')
        if order_id and 'payment_line_ids' in fields_list:
            order = self.env['sale.order'].browse(order_id)
            journal = order.final_payment_journal_id or order.proposed_payment_journal_id
            financing_plan = order.financing_plan_id

            # Solo pre-cargar una línea si el pedido tiene plan o diario definido.
            # Sin ambos el cajero elige el medio de pago desde cero.
            if financing_plan or journal:
                line_type = 'bank'
                if financing_plan and financing_plan.is_pay_later:
                    line_type = 'cc'
                elif financing_plan and financing_plan.is_check_payment:
                    line_type = 'check'
                elif journal and journal.type == 'cash':
                    line_type = 'cash'

                # Las líneas banco requieren un plan en la vista (required=True).
                # Sin plan, pre-llenar banco crea una fila vacía que aparece como
                # "Transferencia seleccionada por defecto". Solo pre-llenamos banco
                # si hay un financing_plan explícito; el efectivo sí puede pre-llenarse
                # sin plan ya que ese campo no es requerido en su sección.
                should_prefill = bool(financing_plan) or line_type == 'cash'
                if should_prefill:
                    # Para líneas banco: el plan es la fuente de verdad del diario.
                    # Si el plan tiene payment_journal_id, ese prevalece sobre el
                    # diario sugerido del pedido, igual que lo hace _complete_multi_payment.
                    if line_type == 'bank' and financing_plan and financing_plan.payment_journal_id:
                        effective_journal = financing_plan.payment_journal_id
                    else:
                        effective_journal = journal
                    res['payment_line_ids'] = [(0, 0, {
                        'sequence': 10,
                        'line_type': line_type,
                        'payment_journal_id': effective_journal.id if effective_journal else False,
                        'financing_plan_id': financing_plan.id if financing_plan else False,
                        'amount': order.amount_total,
                        'cash_received': order.amount_total,
                    })]
        if 'invoice_journal_id' in fields_list and not res.get('invoice_journal_id'):
            sale_journals = self.env['account.journal'].search([
                ('type', '=', 'sale'),
                ('company_id', '=', self.env.company.id),
            ])
            if len(sale_journals) == 1:
                res['invoice_journal_id'] = sale_journals.id
        return res

    @staticmethod
    def _coupon_digits(value):
        return re.sub(r'\D', '', value or '')

    @classmethod
    def _format_coupon_number(cls, value):
        digits = cls._coupon_digits(value)[:7]
        if not digits:
            return False
        if len(digits) <= 3:
            return digits
        return '%s-%s' % (digits[:3], digits[3:])

    def action_confirm_payment(self):
        self.ensure_one()
        if not self.cashier_session_id:
            raise UserError(
                _('No hay una sesión de caja abierta para la empresa de este pedido.\n'
                  'Abrí una desde Caja → Sesiones Abiertas → Nuevo o ingresá desde Sesión Activa.')
            )

        # Limpiar líneas "fantasma" creadas por el OWL al renderizar tablas vacías:
        # - banco/cheque sin financing_plan_id: siempre inválidas (plan es requerido)
        # - cash/resto sin importe y sin plan: filas vacías accidentales
        phantom_lines = self.payment_line_ids.filtered(
            lambda l: (l.line_type in ('bank', 'check') and not l.financing_plan_id)
            or (l.line_type not in ('cc',) and not l.financing_plan_id and not (l.amount or 0.0) > 0)
        )
        if phantom_lines:
            phantom_lines.unlink()

        if not self.payment_line_ids:
            raise UserError(_('Agregá al menos un medio de pago antes de confirmar.'))
        if not self.invoice_journal_id:
            raise UserError(_('Seleccioná el Diario de facturación antes de confirmar el cobro.'))

        # En modo único, contar solo líneas con importe real (CC siempre cuenta).
        real_lines = self.payment_line_ids.filtered(
            lambda l: l.line_type == 'cc' or (l.amount or 0.0) > 0
        )
        if self.payment_mode == 'single' and len(real_lines) > 1:
            raise UserError(_(
                'El modo "Pago único" solo permite una línea de cobro.\n'
                'Cambiá a "Múltiples pagos" o eliminá las líneas extras.'
            ))

        for line in self.payment_line_ids:
            is_cc = line.line_type == 'cc'
            is_check = line.line_type == 'check'
            # El diario puede venir del campo de la línea O del plan de pago.
            effective_journal = (
                line.payment_journal_id
                or (line.financing_plan_id and line.financing_plan_id.payment_journal_id)
            )
            if not effective_journal and not is_cc:
                raise UserError(_('Cada línea de pago debe tener un medio de pago seleccionado.'))
            if not is_cc and not (line.amount or 0.0) > 0:
                raise UserError(_('El importe de cada línea de pago debe ser mayor a cero.'))
            if is_check:
                if not line.check_number:
                    raise UserError(_(
                        'La línea de cheque (%s) requiere número de cheque.'
                    ) % line.financing_plan_id.name)
                if not line.check_payment_date:
                    raise UserError(_(
                        'La línea de cheque (%s) requiere fecha de cobro.'
                    ) % line.financing_plan_id.name)
            if line.coupon_number:
                digits = self._coupon_digits(line.coupon_number)
                if len(digits) != 7:
                    raise UserError(_(
                        'Cupón inválido en la línea "%s". '
                        'Debe tener exactamente 7 dígitos con formato 000-0000.'
                    ) % line.payment_journal_id.name)
                line.coupon_number = '%s-%s' % (digits[:3], digits[3:])
            if line.requires_coupon and not line.coupon_number:
                raise UserError(_(
                    'El plan "%s" requiere número de cupón con formato 000-0000.'
                ) % line.financing_plan_id.name)
            if line.requires_voucher and not line.voucher_number:
                raise UserError(_(
                    'El plan "%s" requiere número de comprobante de transferencia.'
                ) % line.financing_plan_id.name)

        if not self.multi_is_balanced:
            if self.payment_mode == 'single':
                raise UserError(_(
                    'El total ingresado (%.2f) no coincide con el total a cobrar (%.2f).\n'
                    'Diferencia: %.2f. Ajustá los importes antes de confirmar.'
                ) % (self.multi_total, self.total_to_collect, self.multi_remaining))
            else:
                raise UserError(_(
                    'El total ingresado (%.2f) es menor al total del pedido (%.2f).\n'
                    'Falta asignar: %.2f. Agregá o ajustá las líneas de pago.'
                ) % (self.multi_total, self.order_amount_total, self.multi_remaining))

        self.sale_order_id._complete_multi_payment(
            payment_lines=self.payment_line_ids,
            cashier_session=self.cashier_session_id,
            invoice_journal=self.invoice_journal_id or False,
            payment_mode=self.payment_mode,
        )
        order = self.sale_order_id
        invoice = order.invoice_ids.filtered(
            lambda i: i.state == 'posted' and i.move_type == 'out_invoice'
        )[:1]

        auto_print = self.env['ir.config_parameter'].sudo().get_param(
            'sale_op_flow.auto_print_invoice', '0'
        ) in ('1', 'true')
        wizard = self.env['sof.print.wizard'].create({
            'order_id': order.id,
            'invoice_id': invoice.id if invoice else False,
            'auto_print': auto_print and bool(invoice),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cobro registrado'),
            'res_model': 'sof.print.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
