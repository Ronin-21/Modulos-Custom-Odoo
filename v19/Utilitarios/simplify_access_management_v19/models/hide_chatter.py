from odoo import fields, models, api, _
from lxml import etree


class hide_chatter(models.Model):

    def _invalidate_access_management_caches(self):
        self.env.registry.clear_cache()
        self.env.registry.clear_cache('templates')

    _name = 'hide.chatter'
    _description = "Permisos de chatter"

    access_management_id = fields.Many2one('access.management', 'Gestión de accesos')
    model_id = fields.Many2one('ir.model', 'Model')

    hide_chatter = fields.Boolean('Chatter'
                                  ,help="The Chatter will be hidden in selected model from the specified users.")
    hide_send_mail = fields.Boolean('Send Message'
                                ,help="The Send Message button will be hidden in chatter of selected model from the specified users.")
    hide_log_notes = fields.Boolean('Notas internas', help="The Log Notes button will be hidden in chatter of selected model from the specified users.")
    hide_schedule_activity = fields.Boolean('Programar actividad',help="The Schedule Activity button will be hidden in chatter of selected model from the specified users.")

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        self._invalidate_access_management_caches()
        return res

    def write(self, vals):
        res = super().write(vals)
        self._invalidate_access_management_caches()
        return res

    def unlink(self):
        res = super().unlink()
        self._invalidate_access_management_caches()
        return res
