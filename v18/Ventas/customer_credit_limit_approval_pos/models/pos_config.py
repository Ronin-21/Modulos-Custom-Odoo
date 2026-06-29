# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import AccessError


class PosConfig(models.Model):
    _inherit = 'pos.config'

    show_partner_balance = fields.Boolean(
        string="Mostrar saldo de clientes en POS",
        help=(
            "Si está activo, el POS mostrará la columna 'Saldo' en el selector de clientes."
        ),
        default=False,
        groups="customer_credit_limit_approval_pos.group_pos_balance_admin",
    )

    @api.model
    def create(self, vals):
        if 'show_partner_balance' in vals and not self.env.user.has_group(
            'customer_credit_limit_approval_pos.group_pos_balance_admin'
        ):
            raise AccessError(_("No tenés permisos para cambiar 'Mostrar saldo de clientes en POS'."))
        return super().create(vals)

    def write(self, vals):
        if 'show_partner_balance' in vals and not self.env.user.has_group(
            'customer_credit_limit_approval_pos.group_pos_balance_admin'
        ):
            raise AccessError(_("No tenés permisos para cambiar 'Mostrar saldo de clientes en POS'."))
        return super().write(vals)
