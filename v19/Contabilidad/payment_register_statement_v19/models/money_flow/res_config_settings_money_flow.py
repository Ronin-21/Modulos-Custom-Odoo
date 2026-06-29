# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    prs_money_flow_enabled = fields.Boolean(
        string='Flujo de Pagos',
        related='company_id.prs_money_flow_enabled',
        readonly=False,
        help='Activa la agenda de Flujo de Pagos, sus menus y la generacion de flujos proyectados para la empresa actual.',
    )
    def set_values(self):
        res = super().set_values()
        try:
            self.env['payment.provider']._prs_ensure_internal_provider()
        except Exception:
            pass
        # Keep the menu group synchronized without relying on stored columns in res.company.
        group = self.env.ref('payment_register_statement_v19.group_prs_money_flow_enabled', raise_if_not_found=False)
        if group:
            account_users = self.env.ref('account.group_account_user', raise_if_not_found=False)
            enabled_any_company = bool(self.env['res.company'].sudo().search([('prs_money_flow_enabled', '=', True)], limit=1))
            if enabled_any_company:
                if account_users:
                    group.write({'implied_ids': [(4, account_users.id)]})
                    users = self.env['res.users'].sudo().search([('group_ids', 'in', account_users.ids)])
                else:
                    users = self.env['res.users'].sudo().search([])
                users.write({'group_ids': [(4, group.id)]})
            else:
                users = self.env['res.users'].sudo().search([('group_ids', 'in', [group.id])])
                users.write({'group_ids': [(3, group.id)]})
        return res
