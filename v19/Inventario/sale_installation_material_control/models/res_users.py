# -*- coding: utf-8 -*-
from odoo import fields, models

RESPONSIBLE_GROUP = 'sale_installation_material_control.group_installation_responsible'
ADMIN_GROUP = 'sale_installation_material_control.group_installation_admin'


class ResUsers(models.Model):
    _inherit = 'res.users'

    can_validate_installation_material = fields.Boolean(
        string='Puede validar materiales de instalación',
        help='Permite a este usuario registrar retiros y devoluciones de materiales de '
             'instalación. Los administradores de instalación siempre pueden hacerlo.')

    def _can_validate_installation_material(self):
        """True si el usuario puede operar retiros/devoluciones de instalación."""
        self.ensure_one()
        return bool(
            self.can_validate_installation_material
            or self.has_group(RESPONSIBLE_GROUP)
            or self.has_group(ADMIN_GROUP))
