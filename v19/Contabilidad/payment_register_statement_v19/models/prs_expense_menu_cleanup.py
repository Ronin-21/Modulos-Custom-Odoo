# -*- coding: utf-8 -*-
from odoo import api, models, SUPERUSER_ID

class PrsExpenseReportMenuCleanup(models.AbstractModel):
    _name = 'prs.expense.report.menu.cleanup'
    _description = 'Cleanup old Expense Report menus/actions'

    def _register_hook(self):
        # Runs on registry init (including module upgrade). Keep idempotent and safe.
        res = super()._register_hook()
        env = api.Environment(self._cr, SUPERUSER_ID, {})

        # 1) Deactivate old menus created by earlier iterations: "Reporte de gastos (..."
        old = env['ir.ui.menu'].search([('name', 'ilike', 'Reporte de gastos ('), ('active', '=', True)])
        if old:
            old.write({'active': False})

        # 2) Deactivate the previous account_report menu with same label (client action tag=account_report)
        # Keep our new menu (act_window) active.
        menus = env['ir.ui.menu'].search([('name', '=', 'Reporte de gastos'), ('active', '=', True)])
        for m in menus:
            # action is like 'ir.actions.client,123' or 'ir.actions.act_window,456'
            if not m.action:
                continue
            action_model = m.action._name
            if action_model == 'ir.actions.client' and getattr(m.action, 'tag', '') == 'account_report':
                m.write({'active': False})
        return res
