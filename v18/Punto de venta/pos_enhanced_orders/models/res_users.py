# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    pos_can_view_closing_documents = fields.Boolean(
        string="Ver facturas/órdenes desde control de cierre POS",
        compute="_compute_pos_can_view_closing_documents",
        inverse="_inverse_pos_can_view_closing_documents",
        help="Permite usar los botones Ver dentro del asistente de control de facturas del cierre de sesión POS.",
    )

    @api.depends("groups_id")
    def _compute_pos_can_view_closing_documents(self):
        group = self.env.ref(
            "pos_enhanced_orders.group_pos_invoice_closing_view",
            raise_if_not_found=False,
        )
        for user in self:
            user.pos_can_view_closing_documents = bool(group and group in user.groups_id)

    def _inverse_pos_can_view_closing_documents(self):
        group = self.env.ref(
            "pos_enhanced_orders.group_pos_invoice_closing_view",
            raise_if_not_found=False,
        )
        if not group:
            return
        for user in self:
            if user.pos_can_view_closing_documents:
                user.groups_id = [(4, group.id)]
            else:
                user.groups_id = [(3, group.id)]
