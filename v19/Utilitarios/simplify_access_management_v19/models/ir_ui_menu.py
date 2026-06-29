# HOTFIX3 Odoo 19 cache compatibility
from odoo import api, fields, models, _
from odoo.osv import expression


class ir_ui_menu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _get_access_management_hidden_menu_ids(self):
        company_ids = set(self.env.companies.ids or [self.env.company.id])
        access_rules = self.env.user.sudo().access_management_ids.filtered(
            lambda line: line.active and (
                line.is_apply_on_without_company or bool(company_ids.intersection(set(line.company_ids.ids)))
            )
        )
        return list(set(access_rules.mapped('hide_menu_ids.menu_id')))

    @api.model
    def _load_menus_blacklist(self):
        blacklisted_menu_ids = set(super()._load_menus_blacklist())
        blacklisted_menu_ids.update(self._get_access_management_hidden_menu_ids())
        return list(blacklisted_menu_ids)

    @api.model
    def search(self, args, offset=0, limit=None, order=None):
        hidden_menu_ids = self._get_access_management_hidden_menu_ids()
        if hidden_menu_ids:
            args = expression.AND([args, [('id', 'not in', hidden_menu_ids)]])
        return super().search(args, offset=offset, limit=limit, order=order)

    def search_fetch(self, domain, field_names, offset=0, limit=None, order=None):
        hidden_menu_ids = self._get_access_management_hidden_menu_ids()
        if hidden_menu_ids:
            domain = expression.AND([domain, [('id', 'not in', hidden_menu_ids)]])
        return super().search_fetch(domain, field_names, offset=offset, limit=limit, order=order)

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        menu_item_obj = self.env['menu.item'].sudo()
        for record in res:
            menu_item_obj.create({'name': record.display_name, 'menu_id': record.id})
        self.env.registry.clear_cache()
        return res

    def write(self, vals):
        res = super().write(vals)
        menu_item_obj = self.env['menu.item'].sudo()
        for record in self:
            menu_item_obj.search([('menu_id', '=', record.id)]).write({'name': record.display_name})
        self.env.registry.clear_cache()
        return res

    def unlink(self):
        menu_item_obj = self.env['menu.item'].sudo()
        for record in self:
            menu_item_obj.search([('menu_id', '=', record.id)]).unlink()
        self.env.registry.clear_cache()
        return super().unlink()
