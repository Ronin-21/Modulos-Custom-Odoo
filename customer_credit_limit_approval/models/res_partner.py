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
        string='Activar control de crédito',
        help='Activa la validación de límite de crédito para este cliente.'
    )
    credit_warning = fields.Monetary(
        string='Monto de advertencia',
        currency_field='company_currency_id',
        help='Al superar este monto se puede advertir pero no necesariamente bloquear.'
    )
    credit_blocking = fields.Monetary(
        string='Monto de bloqueo',
        currency_field='company_currency_id',
        help='Al superar este monto la orden se bloqueará y deberá aprobarse.'
    )
    amount_due = fields.Monetary(
        string='Importe adeudado',
        currency_field='company_currency_id',
        compute='_compute_amount_due',
        store=False,
        help='Deuda actual del cliente más documentos pendientes.'
    )

    @api.depends('credit', 'debit')
    def _compute_amount_due(self):
        """
        Calcula el monto adeudado del cliente considerando:
        - Saldo contable (debit - credit) -> lo que el cliente nos debe.
        - Órdenes de venta confirmadas no totalmente facturadas.
        """
        SaleOrder = self.env['sale.order']
        for partner in self:
            try:
                # 1) saldo contable del partner
                # en Odoo: debit = lo que me deben, credit = lo que debo
                total_due = (partner.debit or 0.0) - (partner.credit or 0.0)

                # 2) ventas confirmadas no facturadas del partner
                # acotamos por partner y por estado
                sale_orders = SaleOrder.search([
                    ('partner_id', '=', partner.id),
                    ('state', '=', 'sale'),
                    ('invoice_status', '!=', 'invoiced'),
                ])
                for order in sale_orders:
                    if not order.invoice_ids:
                        # sin facturas aún → contamos el total de la orden
                        total_due += order.amount_total
                    else:
                        # con facturas → solo lo que sigue en borrador
                        draft_invoices = order.invoice_ids.filtered(lambda m: m.state == 'draft')
                        if draft_invoices:
                            total_due += sum(draft_invoices.mapped('amount_residual'))

                partner.amount_due = total_due

                _logger.debug(
                    "Partner %s (%s) - amount_due calculado: %s",
                    partner.name, partner.id, partner.amount_due
                )
            except Exception as e:
                _logger.error(
                    "Error al calcular amount_due para partner %s: %s",
                    partner.id, e
                )
                # fallback: al menos el saldo contable
                partner.amount_due = (partner.debit or 0.0) - (partner.credit or 0.0)

    @api.constrains('credit_warning', 'credit_blocking')
    def _check_credit_amount(self):
        """
        Valida que los montos de crédito sean coherentes:
        - warning <= blocking
        - ambos >= 0
        """
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
