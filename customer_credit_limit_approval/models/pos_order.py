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
        - type == 'pay_later' (si existe)
        - tiene cuenta por cobrar configurada (receivable_account_id)
        - flags equivalentes de terceros
        """
        if not payment_method:
            return False
        # 1) selección clásica (depende de versiones/módulos)
        if getattr(payment_method, 'type', False) == 'pay_later':
            return True
        # 2) configuración contable nativa más confiable
        if getattr(payment_method, 'receivable_account_id', False):
            return True
        # 3) flags alternativos comunes
        for attr in ('use_customer_account', 'is_customer_account', 'allow_credit'):
            if getattr(payment_method, attr, False):
                return True
        return False

    def _has_account_payment(self, order_dict):
        """Verifica si la orden tiene pagos ‘cuenta de cliente’."""
        for payment in order_dict.get('payment_ids', []):
            # payment es (0/1/2, id, vals)
            if len(payment) >= 3 and isinstance(payment[2], dict):
                pm_id = self._extract_payment_method_id(payment[2])
                if pm_id:
                    pm = self.env['pos.payment.method'].browse(pm_id)
                    if self._is_customer_account_method(pm):
                        return True
        return False

    def _convert_to_partner_company_currency(self, amount, order_dict, partner):
        """Convierte amount desde moneda del ticket a moneda de la compañía del partner."""
        try:
            Currency = self.env['res.currency']
            company = partner.company_id or self.env.company
            # moneda del pedido (pricelist/pos)
            order_currency_id = order_dict.get('currency_id')
            if isinstance(order_currency_id, (list, tuple)) and order_currency_id:
                order_currency_id = order_currency_id[0]
            order_currency = Currency.browse(order_currency_id) if order_currency_id else (self.currency_id or company.currency_id)
            target_currency = company.currency_id

            if order_currency and target_currency and order_currency.id != target_currency.id:
                # Obtener fecha (hoy) y compañía real del POS si está disponible
                session_id = order_dict.get('session_id') or order_dict.get('pos_session_id')
                pos_company = None
                if session_id:
                    pos_company = self.env['pos.session'].browse(session_id).company_id
                conv_company = pos_company or company
                return order_currency._convert(amount, target_currency, conv_company, fields.Date.context_today(self))
        except Exception as e:
            _logger.warning("No se pudo convertir moneda del POS: %s", e)
        return amount

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
                # ambas en moneda de la compañía del partner (order.amount_total suele estar ya en currency_id del POS)
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
        """True si se debe BLOQUEAR el pago."""
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
        for order in orders:
            # Siempre trabajamos con el dict "plano" (por si viene envuelto como {'data': {...}})
            order = self._normalize_ui_order_dict(order)

            if order.get('state') == 'paid' and self._has_account_payment(order):
                partner_id = order.get('partner_id')
                partner = self.env['res.partner'].browse(partner_id) if partner_id else None

                # NUEVO: si intenta usar Cuenta Corriente y el cliente no tiene credit_check, bloquear.
                if not partner or not partner.credit_check:
                    raise UserError(_(
                        "El cliente no tiene habilitada la Cuenta Corriente.\n\n"
                        "Active “Activar control de crédito” en el contacto para poder usar este método de pago."
                    ))

                # Si tiene credit_check → aplicamos tu control de tope
                total_with_order = (partner.amount_due or 0.0) + (order.get('amount_total', 0.0) or 0.0)
                limit = partner.credit_blocking or 0.0
                front_checked = bool(order.get('credit_checked_front'))

                # Seguridad primero: si EXCEDE, SIEMPRE se bloquea (aunque el front “diga” que pasó).
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
                else:
                    # Si NO excede y el front ya validó, no mostramos nada en backend.
                    if front_checked:
                        continue  # pasa a procesar normalmente

        return super().sync_from_ui(orders)
