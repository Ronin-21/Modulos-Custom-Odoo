# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    mcc_allow_internal_contact_operations = fields.Boolean(
        string="Administrar uso comercial de contactos",
        default=False,
        help=(
            "Si está activo, este usuario puede ver y modificar el bloque Uso comercial "
            "en Contactos. No otorga bypass para usar contactos internos en Ventas, "
            "Compras, Contabilidad ni POS: los checks del contacto aplican para todos."
        ),
    )

    def mcc_can_manage_business_contact_usage(self):
        self.ensure_one()
        return bool(self.mcc_allow_internal_contact_operations)

    def mcc_can_bypass_business_contact_usage(self):
        """Compatibilidad: ya no existe bypass por administrador.

        Los checks comerciales del contacto aplican para todos los usuarios, incluso
        administradores. El check del usuario solo permite administrar/ver esos checks.
        """
        self.ensure_one()
        return False

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users.mapped("partner_id")._mcc_auto_configure_system_contacts()
        return users

    def write(self, vals):
        res = super().write(vals)
        if "partner_id" in vals or "groups_id" in vals or "share" in vals:
            self.env["res.partner"]._mcc_auto_configure_system_contacts()
        return res
