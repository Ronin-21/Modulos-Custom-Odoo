# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Moneda de la compañía para usarla en los Monetary
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
        store=False,
    )

    credit_check = fields.Boolean(
        string='Crédito activo ?',
        help='Activa la validación de límite de crédito para este cliente.'
    )
    credit_warning = fields.Monetary(
        string='Monto de advertencia ?',
        currency_field='company_currency_id',
        help='Al superar este monto se puede advertir pero no necesariamente bloquear.'
    )
    credit_blocking = fields.Monetary(
        string='Monto de bloqueo ?',
        currency_field='company_currency_id',
        help='Al superar este monto la orden se bloqueará y deberá aprobarse.'
    )

    # ─────────────────────────────────────────────
    # DESGLOSE DE DEUDA
    # ─────────────────────────────────────────────
    amount_due_accounting = fields.Monetary(
        string='Deuda facturada (contable)',
        currency_field='company_currency_id',
        compute='_compute_credit_components',
        store=False,
        help='Sólo facturas/movimientos en cuentas a cobrar (debit - credit).'
    )
    amount_due_sale = fields.Monetary(
        string='Ventas confirmadas sin facturar',
        currency_field='company_currency_id',
        compute='_compute_credit_components',
        store=False,
        help='Órdenes de venta en estado Venta no totalmente facturadas.'
    )
    amount_due_pos = fields.Monetary(
        string='POS Cuenta Corriente pendiente',
        currency_field='company_currency_id',
        compute='_compute_credit_components',
        store=False,
        help='Órdenes de PdV en Cuenta Corriente aún no llevadas a contabilidad.'
    )
    amount_due = fields.Monetary(
        string='Deuda Total ?',
        currency_field='company_currency_id',
        compute='_compute_credit_components',
        store=False,
        help='Suma de deuda contable + ventas sin factura + POS Cuenta Corriente.'
    )

    @api.depends('credit', 'debit')
    def _compute_credit_components(self):
        """
        Calcula el desglose de deuda:
        1) amount_due_accounting -> (debit - credit)
        2) amount_due_sale -> SO confirmadas no facturadas
        3) amount_due_pos -> POS Cuenta Corriente sin contabilidad
        4) amount_due -> suma de todo lo anterior
        """
        SaleOrder = self.env['sale.order']
        PosOrder = self.env['pos.order']
        PosPaymentMethod = self.env['pos.payment.method']

        # Método de pago POS "Cuenta Corriente" (ajusta el nombre si en tu base es otro)
        pm_cuenta_corriente = PosPaymentMethod.search([
            ('name', '=', 'Cuenta Corriente')
        ], limit=1)

        if not pm_cuenta_corriente:
            _logger.warning(
                "No se encontró ningún método de pago POS llamado 'Cuenta Corriente'. "
                "amount_due_pos quedará en 0."
            )

        for partner in self:
            try:
                # 1) Deuda contable (facturado)
                accounting = (partner.debit or 0.0) - (partner.credit or 0.0)

                # 2) Ventas confirmadas no facturadas
                sale_amount = 0.0
                sale_orders = SaleOrder.search([
                    ('partner_id', '=', partner.id),
                    ('state', '=', 'sale'),
                    ('invoice_status', '!=', 'invoiced'),
                ])
                for order in sale_orders:
                    if not order.invoice_ids:
                        sale_amount += order.amount_total
                    else:
                        draft_invoices = order.invoice_ids.filtered(
                            lambda m: m.state == 'draft'
                        )
                        if draft_invoices:
                            sale_amount += sum(draft_invoices.mapped('amount_residual'))

                # 3) POS Cuenta Corriente pendiente
                pos_amount = 0.0
                if pm_cuenta_corriente:
                    pos_domain = [
                        ('partner_id', '=', partner.id),
                        ('state', '!=', 'cancel'),
                        ('amount_total', '>', 0),
                        ('payment_ids.payment_method_id', '=', pm_cuenta_corriente.id),
                        # Sólo POS que aún no tienen movimiento contable
                        ('account_move', '=', False),
                    ]
                    pos_orders_cc = PosOrder.search(pos_domain)
                    pos_amount = sum(pos_orders_cc.mapped('amount_total'))

                    _logger.debug(
                        "Partner %s (%s) - POS Cuenta Corriente total: %s (ordenes: %s)",
                        partner.name,
                        partner.id,
                        pos_amount,
                        pos_orders_cc.ids,
                    )

                # Asignamos los componentes
                partner.amount_due_accounting = accounting
                partner.amount_due_sale = sale_amount
                partner.amount_due_pos = pos_amount
                partner.amount_due = accounting + sale_amount + pos_amount

                _logger.debug(
                    "Partner %s (%s) - amount_due_accounting=%s, "
                    "amount_due_sale=%s, amount_due_pos=%s, amount_due_total=%s",
                    partner.name, partner.id,
                    partner.amount_due_accounting,
                    partner.amount_due_sale,
                    partner.amount_due_pos,
                    partner.amount_due,
                )

            except Exception as e:
                _logger.error(
                    "Error al calcular amount_due para partner %s: %s",
                    partner.id, e
                )
                # fallback: solo contable
                accounting = (partner.debit or 0.0) - (partner.credit or 0.0)
                partner.amount_due_accounting = accounting
                partner.amount_due_sale = 0.0
                partner.amount_due_pos = 0.0
                partner.amount_due = accounting

    @api.constrains('credit_warning', 'credit_blocking')
    def _check_credit_amount(self):
        for partner in self:
            warning = partner.credit_warning or 0.0
            blocking = partner.credit_blocking or 0.0

            if warning < 0 or blocking < 0:
                raise ValidationError(
                    _('Los montos de advertencia y bloqueo no pueden ser negativos.')
                )

            if warning and blocking and warning > blocking:
                raise ValidationError(
                    _('El monto de advertencia (%s) no puede ser mayor que el monto de bloqueo (%s).')
                    % (warning, blocking)
                )


class ResCompany(models.Model):
    _inherit = 'res.company'

    accountant_email = fields.Char(string='Accountant email')
