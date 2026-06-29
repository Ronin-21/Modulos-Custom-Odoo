from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Mantener visible solo el menú principal "Reporte de gastos"
    main_menu = env.ref('payment_register_statement.menu_prs_expense_account_report', raise_if_not_found=False)
    if not main_menu:
        return

    # Desactivar cualquier otro menú "Reporte de gastos*" que haya quedado de intentos anteriores
    dup_menus = env['ir.ui.menu'].search([
        ('id', '!=', main_menu.id),
        ('parent_id', '=', main_menu.parent_id.id),
        ('name', 'ilike', 'Reporte de gastos'),
    ])
    if dup_menus:
        dup_menus.write({'active': False})
