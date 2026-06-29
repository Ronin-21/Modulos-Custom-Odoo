# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import AccessError

class PosConfig(models.Model):
    _inherit = 'pos.config'

    show_partner_balance = fields.Boolean(
        string="Mostrar saldo de clientes en POS",
        help=(
            "Si está activo, el POS mostrará la columna 'Saldo' en el selector de clientes. "
            "Si el usuario pertenece al grupo 'POS: Ver saldo de clientes', verá el saldo "
            "aunque este switch esté apagado."
        ),
        default=False,
        groups="customer_credit_limit_approval.group_pos_balance_admin",  # solo ese grupo lo ve en cualquier vista
    )

    @api.model
    def create(self, vals):
        # Si intentan setear el flag en la creación, validar permisos
        if 'show_partner_balance' in vals and not self.env.user.has_group(
            'customer_credit_limit_approval.group_pos_balance_admin'
        ):
            raise AccessError(_("No tenés permisos para cambiar 'Mostrar saldo de clientes en POS'."))
        return super().create(vals)

    def write(self, vals):
        # Solo bloquear si realmente están intentando cambiar el flag
        if 'show_partner_balance' in vals and not self.env.user.has_group(
            'customer_credit_limit_approval.group_pos_balance_admin'
        ):
            raise AccessError(_("No tenés permisos para cambiar 'Mostrar saldo de clientes en POS'."))
        return super().write(vals)
