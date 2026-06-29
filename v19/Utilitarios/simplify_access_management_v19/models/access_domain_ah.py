from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError


class access_domain_ah(models.Model):

    def _invalidate_access_management_caches(self):
        self.env.registry.clear_cache()
        self.env.registry.clear_cache('templates')

    _name = 'access.domain.ah'
    _description = 'Acceso por dominio'

    model_id = fields.Many2one(
        'ir.model', string='Model', index=True, required=True, ondelete='cascade')
    model_name = fields.Char(string='Nombre del modelo', related='model_id.model', readonly=True, store=True)
    apply_domain = fields.Boolean('Apply Filter')
    domain = fields.Char(string='Filtro', default='[]',
                         help="The create customised domain rule where we can customise rule by selecting specific fields and records")

    access_management_id = fields.Many2one('access.management', 'Gestión de accesos')

    read_right = fields.Boolean('Leer', default=True, help="The set 'Leer' access of the selected model for the specified users")
    create_right = fields.Boolean('Crear', help="The set 'Crear' access of the selected model for the specified users")
    write_right = fields.Boolean('Escribir', help="The set 'Escribir' access of the selected model for the specified users")
    delete_right = fields.Boolean('Eliminar', help="The set 'Eliminar' access of the selected model for the specified users")

    @api.onchange('apply_domain')
    def _check_domain(self):
        for rec in self:
            if not rec.apply_domain:
                rec.domain = False

    @api.onchange('read_right')
    def _check_read(self):
        for rec in self:
            if not rec.read_right:
                rec.update({
                'create_right': False,
                'write_right': False,
                'delete_right': False,
                'apply_domain': True,
                'domain': '[["id","=",False]]'
            })

    @api.onchange('create_right')
    def _check_create(self):
        for rec in self:
            if rec.create_right:
                rec.read_right = True
            else:
                rec.delete_right = False

    @api.onchange('write_right')
    def _check_write(self):
        for rec in self:
            if rec.write_right:
                rec.read_right = True
            else:
                rec.delete_right = False

    @api.onchange('delete_right')
    def _check_delete(self):
        for rec in self:
            if rec.delete_right:
                rec.update({'read_right': True, 'write_right': True})

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
