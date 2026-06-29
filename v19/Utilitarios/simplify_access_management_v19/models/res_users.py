from odoo import fields, models, api, _
from odoo.exceptions import UserError, AccessDenied
from .query_prepare import search_data
import logging

_logger = logging.getLogger(__name__)


class res_users(models.Model):
    _inherit = 'res.users'

    access_management_ids = fields.Many2many(
        'access.management',
        'access_management_users_rel_ah',
        'user_id',
        'access_management_id',
        'Access Pack'
    )

    def write(self, vals):
        res = super().write(vals)
        for user in self:
            for access in user.sudo().access_management_ids:
                if user.env.company in access.company_ids and access.readonly:
                    if user.has_group('base.group_system') or user.has_group('base.group_erp_manager'):
                        raise UserError(_('Admin user can not be set as a read-only..!'))
        return res

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for record in res:
            for access in record.sudo().access_management_ids:
                if self.env.company in access.company_ids and access.readonly:
                    if record.has_group('base.group_system') or record.has_group('base.group_erp_manager'):
                        raise UserError(_('Admin user can not be set as a read-only..!'))
        return res

    def _login(self, credential, user_agent_env):
        auth_info = super()._login(credential, user_agent_env)
        try:
            uid = auth_info.get('uid')
            env = self.env(user=uid)
            result = search_data(env['res.users'], 'access.management', condition=('disable_login', '=', True), operator='AND', limit=1)
            if result:
                raise AccessDenied("Login is disabled for this user due to access management settings.")
        except AccessDenied:
            _logger.info("Login failed for login:%s due to access management settings", credential.get('login'))
            raise
        return auth_info
