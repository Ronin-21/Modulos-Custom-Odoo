# -*- coding: utf-8 -*-
import logging
from odoo import api, models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    # (opcionales, sólo lectura para tenerlos en el modelo)
    customer_receivable = fields.Monetary(
        string="Total por cobrar",
        related='partner_id.credit',
        currency_field='currency_id',
        readonly=True,
    )
    customer_blocking_limit = fields.Monetary(
        related='partner_id.credit_blocking',
        currency_field='currency_id',
        readonly=True,
    )
    is_credit_limit_exceeded = fields.Boolean(
        compute='_compute_credit_limit_exceeded',
        store=False,
    )

    # ----------------- helpers -----------------
    def _normalize_ui_order_dict(self, order):
        """Acepta dict plano o {'data': {...}} y devuelve el dict de datos."""
        return order.get('data') or order

    def _extract_payment_method_id(self, payment_vals):
        """Soporta id como int o como [id, display_name]."""
        pm = payment_vals.get('payment_method_id')
        if isinstance(pm, (list, tuple)) and pm:
            return pm[0]
        return pm

    def _is_customer_account_method(self, payment_method):
        """
        Detecta método 'Cuenta de cliente' de forma amplia:
        - type == 'pay_later'
        - tiene cuenta por cobrar configurada (receivable_account_id)
        - flags equivalentes de terceros
        """
        if not payment_method:
            return False
        if getattr(payment_method, 'type', False) == 'pay_later':
            return True
        if getattr(payment_method, 'receivable_account_id', False):
            return True
        for attr in ('use_customer_account', 'is_customer_account', 'allow_credit'):
            if getattr(payment_method, attr, False):
                return True
        return False

    def _has_account_payment(self, order_dict):
        """Verifica si la orden tiene pagos 'cuenta de cliente'."""
        for payment in order_dict.get('payment_ids', []):
            # payment = (0/1/2, id, {vals})
            if len(payment) >= 3 and isinstance(payment[2], dict):
                pm_id = self._extract_payment_method_id(payment[2])
                if pm_id:
                    pm = self.env['pos.payment.method'].browse(pm_id)
                    if self._is_customer_account_method(pm):
                        return True
        return False

    # ----------------- computes -----------------
    @api.depends('amount_total', 'partner_id.credit', 'partner_id.credit_blocking')
    def _compute_credit_limit_exceeded(self):
        for order in self:
            exceeded = False
            partner = order.partner_id
            if partner and partner.credit_check:
                # usamos receivable (credit) como “deuda actual”
                total_with_order = (partner.credit or 0.0) + (order.amount_total or 0.0)

                # conversión de moneda si hace falta
                if (order.currency_id and partner.company_id.currency_id
                        and order.currency_id != partner.company_id.currency_id):
                    total_with_order = (partner.credit or 0.0) + order.currency_id._convert(
                        order.amount_total,
                        partner.company_id.currency_id,
                        order.company_id or partner.company_id or self.env.company,
                        fields.Date.context_today(self),
                    )
                exceeded = total_with_order > (partner.credit_blocking or 0.0)
            order.is_credit_limit_exceeded = exceeded

    def _validate_credit_limit_numbers(self, partner, order_amount, order_currency, company):
        """Devuelve (exceeded: bool, total_with_order: float, limit: float)."""
        limit = partner.credit_blocking or 0.0
        # deuda actual del cliente = receivable
        current_due = partner.credit or 0.0
        total_with_order = current_due + (order_amount or 0.0)

        if (order_currency and partner.company_id.currency_id
                and order_currency != partner.company_id.currency_id):
            total_with_order = current_due + order_currency._convert(
                order_amount,
                partner.company_id.currency_id,
                company or partner.company_id or self.env.company,
                fields.Date.context_today(self),
            )
        return total_with_order > limit, total_with_order, limit

    # ----------------- main override -----------------
    @api.model
    def sync_from_ui(self, orders):
        """
        Valida límite de crédito cuando se usa “Cuenta de cliente”.
        """
        for raw in orders:
            order = self._normalize_ui_order_dict(raw)

            # Sólo órdenes que vienen en estado pagado
            if order.get('state') != 'paid':
                continue

            # ¿la orden tiene algún pago a cuenta corriente?
            if not self._has_account_payment(order):
                continue

            partner_id = order.get('partner_id')
            if not partner_id:
                # si no hay cliente no podemos aplicar crédito
                continue

            partner = self.env['res.partner'].browse(partner_id)
            if not partner.credit_check:
                # el cliente no tiene habilitado el control de crédito
                raise UserError(_("El cliente no tiene habilitada la Cuenta Corriente.\n\n"
                                  "Active 'Crédito activo' en el contacto."))

            exceeded, total_with_order, limit = self._validate_credit_limit_numbers(
                partner=partner,
                order_amount=order.get('amount_total', 0.0) or 0.0,
                order_currency=self.env['res.currency'].browse(order.get('currency_id')) if order.get('currency_id') else None,
                company=self.env.company,
            )
            if exceeded:
                diff = round(total_with_order - limit, 2)
                raise UserError(_(
                    "LÍMITE DE CRÉDITO EXCEDIDO\n\n"
                    "Cliente: %(name)s\n"
                    "Límite de crédito: %(limit).2f\n"
                    "Deuda actual: %(due).2f\n"
                    "Total ticket: %(total).2f\n\n"
                    "EXCESO: %(diff).2f\n\n"
                    "Contacte con el gerente para autorizar."
                ) % {
                    'name': partner.name,
                    'limit': limit,
                    'due': partner.credit or 0.0,
                    'total': order.get('amount_total', 0.0) or 0.0,
                    'diff': diff,
                })

        return super().sync_from_ui(orders)
