from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Mantener solo un menú visible de "Reporte de gastos"
    main_menu = env.ref('payment_register_statement.menu_prs_expense_account_report', raise_if_not_found=False)
    if main_menu and main_menu.parent_id:
        dup_menus = env['ir.ui.menu'].search([
            ('id', '!=', main_menu.id),
            ('parent_id', '=', main_menu.parent_id.id),
            ('name', '=', main_menu.name),
        ])
        if dup_menus:
            dup_menus.write({'active': False})

    # Desactivar acciones duplicadas con el mismo nombre (por upgrades previos)
    main_action = env.ref('payment_register_statement.action_prs_expense_account_report', raise_if_not_found=False)
    if main_action:
        dup_actions = env['ir.actions.client'].search([
            ('id', '!=', main_action.id),
            ('name', '=', main_action.name),
        ])
        if dup_actions:
            dup_actions.write({'active': False})
