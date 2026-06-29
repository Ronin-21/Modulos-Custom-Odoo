# -*- coding: utf-8 -*-
"""
Puente: límite de crédito (customer_credit_limit_approval_v19) × flujo
operativo de caja (sale_op_flow).

En el flujo SOF, "confirmar" un pedido sólo lo manda a la cola del cajero
(todavía no se eligió efectivo vs Cuenta Corriente). Por eso el control de
crédito NO debe dispararse al confirmar, sino en el COBRO, y sólo cuando se
usa una línea de Cuenta Corriente (pago diferido / line_type == 'cc').
"""
import logging

from odoo import models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ──────────────────────────────────────────────────────────────────────
    # 1) Neutralizar el control de CLA al CONFIRMAR, sólo para pedidos SOF.
    #    (En pedidos de venta estándar el control sigue intacto.)
    # ──────────────────────────────────────────────────────────────────────
    def _validate_credit_limit(self):
        # Para pedidos del flujo operativo, no abrir el wizard de aprobación
        # al confirmar: el control se hace en el cobro de caja.
        if self.is_sof_order:
            return False
        return super()._validate_credit_limit()

    def _check_salesperson_permission(self):
        # SOF tiene su propio modelo de roles (vendedor / cajero / supervisor);
        # la restricción de "vendedor asignado" de CLA no aplica a estos pedidos.
        if self.is_sof_order:
            return
        return super()._check_salesperson_permission()

    def action_confirm(self):
        # En SOF el control de crédito se hace en el cobro de caja, no al confirmar.
        # Además del wizard de BLOQUEO (ya neutralizado vía _validate_credit_limit),
        # hay que evitar el wizard de ADVERTENCIA: lo silenciamos para pedidos SOF.
        records = self
        if not self.env.context.get('credit_warning_acknowledged') and all(o.is_sof_order for o in self):
            records = self.with_context(credit_warning_acknowledged=True)
        return super(SaleOrder, records).action_confirm()

    # ──────────────────────────────────────────────────────────────────────
    # 2) Evaluación del crédito para una venta en Cuenta Corriente.
    # ──────────────────────────────────────────────────────────────────────
    def _ccl_cc_status(self, cc_amount):
        """Clasifica una venta CC respecto del límite del cliente.

        Devuelve (status, projected, limit, excess) donde status es:
        - 'block_no_cc' : el cliente no tiene 'Crédito activo' → bloqueo duro.
        - 'ok'          : con crédito activo y dentro del límite.
        - 'confirm'     : excede el límite → requiere autorización con PIN de un
                          supervisor (independiente del usuario logueado).

        Deuda proyectada sin doble conteo: amount_due ya incluye este pedido
        (state='sale', sin facturar). Le sacamos el total del pedido y sumamos
        sólo la parte que efectivamente va a Cuenta Corriente.
        """
        self.ensure_one()
        partner = self.partner_id
        if not partner.credit_check:
            return ('block_no_cc', 0.0, 0.0, 0.0)

        base_debt = (partner.amount_due or 0.0) - (self.amount_total or 0.0)
        projected = base_debt + (cc_amount or 0.0)
        limit = partner.credit_blocking or 0.0
        if projected <= limit:
            return ('ok', projected, limit, 0.0)

        excess = round(projected - limit, 2)
        return ('confirm', projected, limit, excess)

    def _ccl_enforce_cc(self, cc_amount, authorized=False):
        """Aplica las reglas de crédito en el cobro (red de seguridad server-side).

        - 'block_no_cc' → bloqueo duro.
        - 'confirm'     → requiere que un supervisor haya autorizado con PIN
                          (authorized=True); si no, se frena.
        - 'ok'          → no hace nada.
        """
        self.ensure_one()
        status, projected, limit, excess = self._ccl_cc_status(cc_amount)
        partner = self.partner_id

        if status == 'block_no_cc':
            raise UserError(_(
                "El cliente «%s» no tiene la Cuenta Corriente habilitada.\n\n"
                "No se puede cobrar con Cuenta Corriente. Activá «Crédito activo» "
                "en la pestaña «Cuenta corriente» del contacto."
            ) % partner.display_name)

        if status == 'confirm':
            if not authorized:
                raise UserError(_(
                    "Esta venta en Cuenta Corriente excede el límite de crédito "
                    "y requiere la autorización (PIN) de un supervisor."
                ))
            emp_id = self.env.context.get('ccl_authorized_by_employee_id')
            emp = self.env['hr.employee'].sudo().browse(emp_id) if emp_id else False
            authorizer = emp.name if emp else self.env.user.name
            self.message_post(body=_(
                "⚠️ Venta en Cuenta Corriente <b>autorizada por %(who)s</b> (PIN) "
                "pese a exceder el límite de crédito.<br/>"
                "Límite: %(limit).2f · Deuda proyectada: %(proj).2f · Exceso: %(exc).2f"
            ) % {
                'who': authorizer,
                'limit': limit,
                'proj': projected,
                'exc': excess,
            })

    def _ccl_open_cashier_confirm(self, payment_wizard, cc_amount):
        """Abre el wizard de confirmación del supervisor para una venta CC sobre el límite."""
        self.ensure_one()
        _status, projected, limit, excess = self._ccl_cc_status(cc_amount)
        wiz = self.env['ccl.cashier.credit.approval'].create({
            'payment_wizard_id': payment_wizard.id,
            'sale_order_id': self.id,
            'partner_id': self.partner_id.id,
            'currency_id': self.currency_id.id,
            'credit_blocking': limit,
            'projected_debt': projected,
            'excess': excess,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Autorización de Cuenta Corriente'),
            'res_model': 'ccl.cashier.credit.approval',
            'res_id': wiz.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ──────────────────────────────────────────────────────────────────────
    # 3) Red de seguridad en el cobro (por si se llama fuera del wizard).
    # ──────────────────────────────────────────────────────────────────────
    def _complete_multi_payment(self, payment_lines, cashier_session,
                                invoice_journal=None, payment_mode='single'):
        cc_lines = payment_lines.filtered(lambda l: l.line_type == 'cc')
        if cc_lines:
            self._ccl_enforce_cc(
                sum(line.amount for line in cc_lines),
                authorized=bool(self.env.context.get('ccl_supervisor_authorized')),
            )
        return super()._complete_multi_payment(
            payment_lines,
            cashier_session,
            invoice_journal=invoice_journal,
            payment_mode=payment_mode,
        )

    def _complete_payment(self, payment_journal, financing_plan, cashier_session,
                          coupon_number=False, invoice_journal=None):
        if financing_plan and financing_plan.is_pay_later:
            self._ccl_enforce_cc(
                self.amount_total or 0.0,
                authorized=bool(self.env.context.get('ccl_supervisor_authorized')),
            )
        return super()._complete_payment(
            payment_journal,
            financing_plan,
            cashier_session,
            coupon_number=coupon_number,
            invoice_journal=invoice_journal,
        )
