from odoo import http
from odoo.addons.web.controllers.export import Export
from odoo.http import request


class Export(Export):

    @http.route('/web/export/get_fields', type='jsonrpc', auth='user', readonly=True)
    def get_fields(self, model, domain, prefix='', parent_name='',
                   import_compat=True, parent_field_type=None,
                   parent_field=None, exclude=None):
        result = super().get_fields(
            model,
            domain,
            prefix=prefix,
            parent_name=parent_name,
            import_compat=import_compat,
            parent_field_type=parent_field_type,
            parent_field=parent_field,
            exclude=exclude,
        )

        invisible_field_ids = request.env['hide.field'].sudo().search([
            ('model_id.model', '=', model),
            ('access_management_id.active', '=', True),
            ('access_management_id.user_ids', 'in', request.env.user.id),
            ('invisible', '=', True),
        ])
        invisible_field_ids -= invisible_field_ids.filtered(
            lambda x: not x.access_management_id.is_apply_on_without_company
            and request.env.company.id not in x.access_management_id.company_ids.ids
        )
        invisible_field_list = set(invisible_field_ids.mapped('field_id.name'))
        return [field for field in result if field.get('id') not in invisible_field_list]
