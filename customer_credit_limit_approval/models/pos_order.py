# -*- coding: utf-8 -*-
import logging
from odoo import api, models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    amount_due = fields.Monetary(
        related='partner_id.amount_due',
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

    # ---------- helpers ----------
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
            if len(payment) >= 3 and isinstance(payment[2], dict):
                pm_id = self._extract_payment_method_id(payment[2])
                if pm_id:
                    pm = self.env['pos.payment.method'].browse(pm_id)
                    if self._is_customer_account_method(pm):
                        return True
        return False

    # ---------- computes ----------
    @api.depends(
        'amount_due',
        'amount_total',
        'partner_id.credit_check',
        'partner_id.credit_blocking',
    )
    def _compute_credit_limit_exceeded(self):
        for order in self:
            exceeded = False
            partner = order.partner_id
            if partner and partner.credit_check:
                total_with_order = (partner.amount_due or 0.0) + (order.amount_total or 0.0)
                if order.currency_id and partner.company_id.currency_id and order.currency_id != partner.company_id.currency_id:
                    total_with_order = (partner.amount_due or 0.0) + order.currency_id._convert(
                        order.amount_total,
                        partner.company_id.currency_id,
                        order.company_id or partner.company_id or self.env.company,
                        fields.Date.context_today(self),
                    )
                exceeded = total_with_order > (partner.credit_blocking or 0.0)
            order.is_credit_limit_exceeded = exceeded

    def _validate_credit_limit(self):
        """Valida si la orden excede el límite de crédito."""
        self.ensure_one()
        partner = self.partner_id
        if not (partner and partner.credit_check):
            return False

        total_with_order = (partner.amount_due or 0.0) + (self.amount_total or 0.0)
        if self.currency_id and partner.company_id.currency_id and self.currency_id != partner.company_id.currency_id:
            total_with_order = (partner.amount_due or 0.0) + self.currency_id._convert(
                self.amount_total,
                partner.company_id.currency_id,
                self.company_id or partner.company_id or self.env.company,
                fields.Date.context_today(self),
            )
        return total_with_order > (partner.credit_blocking or 0.0)

    # ---------- main override ----------
    @api.model
    def sync_from_ui(self, orders):
        """Sincroniza órdenes desde el POS al backend con validación de crédito."""
        for order in orders:
            # Normalizar el dict de la orden
            order = self._normalize_ui_order_dict(order)

            # Validar solo si la orden está pagada Y usa método "Cuenta de cliente"
            if order.get('state') == 'paid' and self._has_account_payment(order):
                partner_id = order.get('partner_id')
                partner = self.env['res.partner'].browse(partner_id) if partner_id else None

                # 1. Validar que el cliente tenga crédito habilitado
                if not partner or not partner.credit_check:
                    raise UserError(_(
                        "El cliente no tiene habilitada la Cuenta Corriente.\n\n"
                        "Active 'Activar control de crédito' en el contacto para poder usar este método de pago."
                    ))

                # 2. Validar que no exceda el límite de crédito
                total_with_order = (partner.amount_due or 0.0) + (order.get('amount_total', 0.0) or 0.0)
                limit = partner.credit_blocking or 0.0

                if total_with_order > limit:
                    diff = round(total_with_order - limit, 2)
                    raise UserError(_(
                        "LÍMITE DE CRÉDITO EXCEDIDO\n\n"
                        "Cliente: %(name)s\n"
                        "Límite de crédito: %(limit).2f\n"
                        "Monto adeudado: %(due).2f\n"
                        "Total ticket: %(total).2f\n\n"
                        "EXCESO: %(diff).2f\n\n"
                        "Contacte con el gerente para autorizar."
                    ) % {
                        'name': partner.name,
                        'limit': limit,
                        'due': partner.amount_due or 0.0,
                        'total': order.get('amount_total', 0.0) or 0.0,
                        'diff': diff,
                    })

        return super().sync_from_ui(orders)