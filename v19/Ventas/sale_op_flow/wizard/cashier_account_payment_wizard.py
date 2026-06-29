# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaleCashierAccountPaymentWizard(models.TransientModel):
    _name = 'sale.cashier.account.payment.wizard'
    _description = 'Cobranza de Cuenta Corriente en Caja'

    partner_id = fields.Many2one('res.partner', string='Cliente', required=True)
    cashier_session_id = fields.Many2one('sale.cashier.session', string='Sesión de caja', readonly=True)
    session_info = fields.Char(string='Sesión activa', readonly=True)
    company_id = fields.Many2one('res.company', string='Sucursal', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)

    partner_total_due = fields.Monetary(
        string='Saldo por cobrar (facturas)', compute='_compute_partner_data', readonly=True,
        currency_field='currency_id',
        help='Saldo por cobrar del cliente según las facturas abiertas (deuda contable). '
             'Es global: incluye la deuda de todas las sucursales. No incluye ventas '
             'confirmadas aún sin facturar (eso es proyección de riesgo del módulo de crédito).',
    )
    open_invoice_ids = fields.Many2many(
        'account.move', string='Facturas abiertas de esta sucursal',
        compute='_compute_partner_data',
        help='Facturas pendientes de pago emitidas por tu sucursal. No se muestran las de '
             'otras sucursales (administración las concilia).',
    )
    amount = fields.Monetary(string='Monto a cobrar', currency_field='currency_id')
    payment_journal_id = fields.Many2one(
        'account.journal', string='Medio de pago',
        domain="[('type', 'in', ['bank', 'cash']), ('company_id', '=', company_id)]",
    )
    memo = fields.Text(
        string='Nota / Concepto', required=True,
        help='Obligatorio: aclará a qué corresponde el pago para que administración pueda '
             'conciliarlo contra las facturas correspondientes.',
    )

    @api.model
    def _get_open_session(self):
        """Sesión de caja abierta de la compañía del cajero (mismo criterio que el cobro)."""
        Session = self.env['sale.cashier.session'].sudo()
        ctx_session_id = (
            self.env.context.get('sof_cashier_session_id')
            or self.env.context.get('default_cashier_session_id')
        )
        if ctx_session_id:
            selected = Session.browse(ctx_session_id).exists()
            if selected and selected.state == 'open':
                return selected
        company = self.env.company
        session = Session.search([('state', '=', 'open'), ('company_id', '=', company.id)], limit=1)
        if session:
            return session
        return Session.search([('state', '=', 'open'), ('company_id', 'in', self.env.companies.ids)], limit=1)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        session = self._get_open_session()
        company = session.company_id if session else self.env.company
        res['cashier_session_id'] = session.id if session else False
        res['session_info'] = session.name if session else _('Sin sesión abierta')
        res['company_id'] = company.id
        res['currency_id'] = company.currency_id.id
        return res

    @api.depends('partner_id', 'company_id')
    def _compute_partner_data(self):
        Move = self.env['account.move']
        for wiz in self:
            partner = wiz.partner_id.commercial_partner_id
            if partner and wiz.company_id:
                # Deuda total GLOBAL: 'credit' es nativo de account y está restringido por
                # grupos, por eso se lee con sudo(). El receivable es compartido entre
                # sucursales, así que el valor es el mismo en cualquier compañía.
                wiz.partner_total_due = partner.with_company(wiz.company_id).sudo().credit
                # Facturas abiertas SOLO de la sucursal de la sesión (sin sudo: respeta las
                # reglas multi-compañía, el cajero no ve facturas de otras sucursales).
                wiz.open_invoice_ids = Move.search([
                    ('move_type', '=', 'out_invoice'),
                    ('state', '=', 'posted'),
                    ('payment_state', 'not in', ('paid', 'reversed')),
                    ('company_id', '=', wiz.company_id.id),
                    ('commercial_partner_id', '=', partner.id),
                ])
            else:
                wiz.partner_total_due = 0.0
                wiz.open_invoice_ids = False

    def action_confirm(self):
        self.ensure_one()
        session = self.cashier_session_id
        if not session or session.state != 'open':
            raise UserError(
                _('No hay una sesión de caja abierta para tu sucursal.\n'
                  'Abrí una desde Caja → Mi Sesión → Nuevo o ingresá desde Sesión Activa.')
            )
        if not self.partner_id:
            raise UserError(_('Seleccioná el cliente.'))
        if not self.payment_journal_id:
            raise UserError(_('Seleccioná el medio de pago.'))
        if (self.amount or 0.0) <= 0:
            raise UserError(_('El monto a cobrar debe ser mayor a cero.'))
        if not (self.memo and self.memo.strip()):
            raise UserError(_('La nota / concepto es obligatoria.'))

        Payment = self.env['account.payment']
        payment_vals = {
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_id.commercial_partner_id.id,
            'amount': self.amount,
            'journal_id': self.payment_journal_id.id,
            'date': fields.Date.today(),
            'currency_id': self.company_id.currency_id.id,
            'company_id': self.company_id.id,
            'op_cashier_session_id': session.id,
        }
        if 'memo' in Payment._fields:
            payment_vals['memo'] = self.memo
        elif 'ref' in Payment._fields:
            payment_vals['ref'] = self.memo

        payment = Payment.create(payment_vals)
        # NO se concilia contra facturas: administración concilia después. El pago entrante
        # ya reduce el saldo por cobrar y entra a la caja (se cuenta en el cierre por
        # op_cashier_session_id).
        payment.action_post()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Pago a cuenta registrado'),
                'message': _('Pago de %(amount).2f registrado para %(partner)s. La deuda se actualizó.') % {
                    'amount': self.amount,
                    'partner': self.partner_id.display_name,
                },
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
