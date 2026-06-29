from odoo import fields, models, api, _
from lxml import etree


class hide_field(models.Model):

    def _invalidate_access_management_caches(self):
        self.env.registry.clear_cache()
        self.env.registry.clear_cache('templates')

    _name = 'hide.field'
    _description = "Permisos de campos"

    access_management_id = fields.Many2one('access.management', 'Gestión de accesos')

    model_id = fields.Many2one('ir.model', 'Model')

    field_id = fields.Many2many('ir.model.fields', 'hide_field_ir_model_fields_rel', 'hide_field_id', 'ir_field_id',
                                'Field')

    invisible = fields.Boolean('Invisible', help="Selected Field will be hidden in selected model from the defined users.")
    readonly = fields.Boolean('Solo lectura', help="Selected Field will be Read only in selected model from the defined users.")
    required = fields.Boolean('Requerido', help="Selected Field will be set as required for selected model from the defined users.")
    external_link = fields.Boolean('Quitar enlace externo', help="External Link will be hidden for relational fields in selected model from the defined users.")


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
