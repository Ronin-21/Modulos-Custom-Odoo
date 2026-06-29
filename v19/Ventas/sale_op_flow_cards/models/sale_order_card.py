# -*- coding: utf-8 -*-
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

_OPERATIONAL_STATES = [
    ('quotation', 'Presupuesto'),
    ('confirmed', 'Confirmado'),
    ('prepared', 'Preparado'),
    ('paid', 'Pagado'),
    ('dispatched', 'Despachado'),
    ('cancelled', 'Cancelado'),
]


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ── Campos de sugerencia de tarjeta (vendedor) ────────────────────────────

    prs_card_provider_id = fields.Many2one(
        'prs.card.provider',
        related='proposed_payment_journal_id.prs_card_provider_id',
        store=False,
        string='Procesador',
    )
    prs_card_id = fields.Many2one(
        'account.card',
        string='Tarjeta sugerida',
        domain="[('provider_id', '=', prs_card_provider_id), ('active', '=', True)]",
        ondelete='set null',
        copy=False,
        tracking=True,
    )
    prs_installment_id = fields.Many2one(
        'account.card.installment',
        string='Plan sugerido',
        domain="[('card_id', '=', prs_card_id), ('active', '=', True)]",
        ondelete='set null',
        copy=False,
        tracking=True,
    )

    # ── Campos informativos computados (para mostrar al cliente) ──────────────

    prs_surcharge_rate = fields.Float(
        string='Recargo (%)',
        compute='_compute_prs_card_display',
        digits=(5, 2),
    )
    prs_surcharge_amount = fields.Monetary(
        string='Monto recargo',
        compute='_compute_prs_card_display',
        currency_field='currency_id',
    )
    prs_total_with_surcharge = fields.Monetary(
        string='Total con recargo',
        compute='_compute_prs_card_display',
        currency_field='currency_id',
    )
    prs_installment_count = fields.Integer(
        string='Cuotas',
        compute='_compute_prs_card_display',
    )
    prs_amount_per_installment = fields.Monetary(
        string='Valor por cuota',
        compute='_compute_prs_card_display',
        currency_field='currency_id',
    )
    prs_commission_passthrough_rate = fields.Float(
        string='Comisión trasladada (%)',
        compute='_compute_prs_card_display',
        digits=(5, 2),
        help='Porcentaje de comisión incluido en el recargo total cuando "Trasladar com." está activo.',
    )

    @api.depends(
        'prs_installment_id',
        'prs_installment_id.surcharge_coefficient',
        'prs_installment_id.divisor',
        'prs_installment_id.apply_commission_surcharge',
        'prs_installment_id.fee_percent',
        'prs_installment_id.fee_tax_percent',
        'prs_installment_id.bank_discount',
        'amount_total',
        'amount_untaxed',
    )
    def _compute_prs_card_display(self):
        for order in self:
            installment = order.prs_installment_id
            divisor = (installment.divisor or 1) if installment else 1
            if not installment:
                order.prs_surcharge_rate = 0.0
                order.prs_commission_passthrough_rate = 0.0
                order.prs_surcharge_amount = 0.0
                order.prs_total_with_surcharge = order.amount_total
                order.prs_installment_count = 0
                order.prs_amount_per_installment = 0.0
                continue

            effective_coef = installment._sof_effective_coefficient()
            base_coef = installment.surcharge_coefficient or 1.0

            # Tasa de comisión trasladada = diferencia entre coeficiente efectivo y base
            commission_rate = round((effective_coef / base_coef - 1.0) * 100, 2) if base_coef else 0.0

            if effective_coef <= 1.0:
                order.prs_surcharge_rate = 0.0
                order.prs_commission_passthrough_rate = 0.0
                order.prs_surcharge_amount = 0.0
                order.prs_total_with_surcharge = order.amount_total
                order.prs_installment_count = divisor
                order.prs_amount_per_installment = (
                    round(order.amount_total / divisor, 2) if divisor else 0.0
                )
                continue

            surcharge = order.amount_untaxed * (effective_coef - 1.0)
            total = order.amount_total + surcharge
            order.prs_surcharge_rate = round((effective_coef - 1.0) * 100, 2)
            order.prs_commission_passthrough_rate = commission_rate
            order.prs_surcharge_amount = round(surcharge, 2)
            order.prs_total_with_surcharge = round(total, 2)
            order.prs_installment_count = divisor
            order.prs_amount_per_installment = round(total / divisor, 2) if divisor else 0.0

    @api.onchange('proposed_payment_journal_id')
    def _onchange_journal_prs_card_sof(self):
        self.prs_card_id = False
        self.prs_installment_id = False

    @api.onchange('prs_card_id')
    def _onchange_prs_card_sof(self):
        self.prs_installment_id = False

    # ── Cobro con tarjeta ─────────────────────────────────────────────────────

    def _complete_multi_payment(self, payment_lines, cashier_session,
                                invoice_journal=None, payment_mode='single'):
        card_lines = [
            l for l in payment_lines
            if getattr(l, 'prs_card_id', False) or getattr(l, 'prs_installment_id', False)
        ]
        if not card_lines:
            return super()._complete_multi_payment(
                payment_lines, cashier_session, invoice_journal, payment_mode
            )

        self.ensure_one()
        if self.operational_state not in ('confirmed', 'prepared'):
            raise UserError(
                _('El pedido "%s" no está disponible para cobro (estado: %s).')
                % (self.name, dict(_OPERATIONAL_STATES).get(
                    self.operational_state, self.operational_state
                ))
            )

        invoice = self._get_or_create_draft_invoice(journal=invoice_journal)
        if not invoice:
            raise UserError(
                _('No se pudo crear la factura para "%s". '
                  'Verificá que los productos tienen política de facturación "Pedido".') % self.name
            )

        if payment_mode == 'single':
            self._apply_card_installment_adjustment(card_lines[0].prs_installment_id, invoice)
        else:
            # En modo multi, ajustar la factura SOLO por el recargo de cuotas de tarjeta.
            # El exceso de cheques u otros medios NO se suma a la factura: queda como
            # crédito a favor del cliente vía reconciliación parcial natural.
            card_surcharge = 0.0
            for card_line in card_lines:
                installment = getattr(card_line, 'prs_installment_id', False)
                if installment:
                    coef = installment._sof_effective_coefficient()
                    amt = card_line.amount or 0.0
                    if coef > 1.0 and amt > 0:
                        card_surcharge += amt - round(amt / coef, 2)
            card_surcharge = round(card_surcharge, 2)
            if card_surcharge > 0.01:
                self._apply_card_fixed_adjustment(invoice, card_surcharge)

        invoice.write({'invoice_date': fields.Date.today()})
        invoice.action_post()

        Payment = self.env['account.payment']
        payments = Payment
        payment_memo = '%s - %s' % (self.name, invoice.name or '')

        for line in payment_lines:
            if line.line_type == 'cc':
                continue

            effective_journal = line.payment_journal_id
            if line.financing_plan_id and line.financing_plan_id.payment_journal_id:
                effective_journal = line.financing_plan_id.payment_journal_id

            payment_vals = {
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': invoice.partner_id.commercial_partner_id.id,
                'amount': line.amount,
                'journal_id': effective_journal.id,
                'date': fields.Date.today(),
                'currency_id': invoice.currency_id.id,
                'company_id': self.company_id.id,
                'op_sale_order_id': self.id,
                'op_cashier_session_id': cashier_session.id if cashier_session else False,
                'op_financing_plan_id': line.financing_plan_id.id if line.financing_plan_id else False,
                'op_coupon_number': line.coupon_number or False,
            }
            installment = getattr(line, 'prs_installment_id', False)
            card = getattr(line, 'prs_card_id', False)
            if installment:
                payment_vals['prs_installment_id'] = installment.id
            if card:
                payment_vals['prs_card_id'] = card.id

            if line.line_type == 'check':
                pml = effective_journal.inbound_payment_method_line_ids.filtered(
                    lambda m: m.code == 'new_third_party_checks'
                )[:1]
                if not pml:
                    raise UserError(_(
                        'El diario "%s" no tiene configurado el método '
                        '"Cheques de terceros recibidos".\n'
                        'Activalo desde Contabilidad → Diarios → %s → Pagos entrantes.'
                    ) % (effective_journal.name, effective_journal.name))
                payment_vals['payment_method_line_id'] = pml.id
                check_number = (line.check_number or '').strip().zfill(8) if line.check_number else False
                payment_vals['l10n_latam_new_check_ids'] = [Command.create({
                    'name': check_number or False,
                    'bank_id': line.check_bank_id.id if line.check_bank_id else False,
                    'issuer_vat': line.check_issuer_vat or False,
                    'payment_date': line.check_payment_date or fields.Date.today(),
                    'amount': line.amount,
                })]

            if 'memo' in Payment._fields:
                payment_vals['memo'] = payment_memo
            elif 'ref' in Payment._fields:
                payment_vals['ref'] = payment_memo

            payment = Payment.create(payment_vals)
            payment.action_post()
            payments |= payment

        self._reconcile_payments_to_invoice(invoice, payments)

        first_line = payment_lines[:1]
        self.write({
            'final_payment_journal_id': first_line.payment_journal_id.id if first_line else False,
            'financing_plan_id': (
                first_line.financing_plan_id.id
                if first_line and first_line.financing_plan_id else False
            ),
            'operational_state': 'paid',
            'cashier_session_id': cashier_session.id if cashier_session else False,
            'collected_by': self.env.uid,
            'collected_date': fields.Datetime.now(),
        })

        journal_names = ', '.join(dict.fromkeys(l.payment_journal_id.name for l in payment_lines))
        self.message_post(
            body=_('Cobrado por <b>%s</b>. Medios: %s | Total: %s %.2f<br/>Listo para despacho.')
            % (self.env.user.name, journal_names, self.currency_id.symbol, invoice.amount_total)
        )
        return payments

    def _apply_card_installment_adjustment(self, installment, invoice):
        """Línea de recargo en factura calculada desde surcharge_coefficient del plan de cuotas."""
        self.ensure_one()
        if invoice.state != 'draft':
            raise UserError(_('La factura ya fue validada.'))
        old_adj = invoice.invoice_line_ids.filtered(lambda l: l.is_sof_adjustment_line)
        if old_adj:
            old_adj.unlink()
        coef = installment._sof_effective_coefficient() if installment else 1.0
        if coef <= 1.0:
            return
        product = self.company_id.sof_card_surcharge_product_id
        if not product:
            # Fallback: usar el producto de la empresa madre si la sucursal no lo tiene configurado
            parent = self.company_id.parent_id
            while parent and not product:
                product = parent.sof_card_surcharge_product_id
                parent = parent.parent_id
        if not product:
            raise UserError(_(
                'Configurá el "Producto recargo tarjeta" en Operaciones de Venta → '
                'Configuración antes de cobrar con tarjeta con recargo.'
            ))
        base = invoice.amount_untaxed
        price_unit = round(base * (coef - 1.0), 2)
        rate_pct = round((coef - 1.0) * 100, 2)
        label = _('Recargo %s (%.2f%%)') % (installment.display_name, rate_pct)
        account = (
            product.property_account_income_id
            or product.categ_id.property_account_income_categ_id
            or invoice.journal_id.default_account_id
        )
        if not account:
            raise UserError(_('Sin cuenta contable para el producto "%s".') % product.name)
        invoice.write({'invoice_line_ids': [(0, 0, {
            'product_id': product.id,
            'name': label,
            'quantity': 1.0,
            'price_unit': price_unit,
            'account_id': account.id,
            'tax_ids': [(5, 0, 0)],
            'is_sof_adjustment_line': True,
        })]})

    def _apply_card_fixed_adjustment(self, invoice, amount):
        """Línea de recargo fijo en factura para cobros multi-pago con tarjeta."""
        self.ensure_one()
        if invoice.state != 'draft':
            raise UserError(_('La factura ya fue validada.'))
        old_adj = invoice.invoice_line_ids.filtered(lambda l: l.is_sof_adjustment_line)
        if old_adj:
            old_adj.unlink()
        if abs(amount) <= 0.01:
            return
        product = self.company_id.sof_card_surcharge_product_id
        if not product:
            # Fallback: usar el producto de la empresa madre si la sucursal no lo tiene configurado
            parent = self.company_id.parent_id
            while parent and not product:
                product = parent.sof_card_surcharge_product_id
                parent = parent.parent_id
        if not product:
            raise UserError(_(
                'Configurá el "Producto recargo tarjeta" en Operaciones de Venta → '
                'Configuración antes de cobrar con tarjeta con recargo.'
            ))
        account = (
            product.property_account_income_id
            or product.categ_id.property_account_income_categ_id
            or invoice.journal_id.default_account_id
        )
        if not account:
            raise UserError(_('Sin cuenta contable para el producto "%s".') % product.name)
        label = _('Recargo por medio de pago') if amount > 0 else _('Descuento por medio de pago')
        invoice.write({'invoice_line_ids': [(0, 0, {
            'product_id': product.id,
            'name': label,
            'quantity': 1.0,
            'price_unit': amount,
            'account_id': account.id,
            'tax_ids': [(5, 0, 0)],
            'is_sof_adjustment_line': True,
        })]})
