from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    enable_volume_discount = fields.Boolean(
        string="Habilitar descuentos por volumen",
        config_parameter="sales_total_units.enable_volume_discount",
        implied_group="sales_total_units.group_volume_discount_feature",
        help="Activa el sistema de descuentos automáticos por litros/unidades vendidas en las órdenes de venta.",
    )

    def set_values(self):
        res = super().set_values()

        group = self.env.ref("sales_total_units.group_volume_discount_feature", raise_if_not_found=False)
        internal = self.env.ref("base.group_user", raise_if_not_found=False)

        if group and internal:
            internal = internal.sudo()
            group = group.sudo()

            if self.enable_volume_discount:
                internal.write({"implied_ids": [(4, group.id)]})
            else:
                internal.write({"implied_ids": [(3, group.id)]})
                # Si quedó asignado directo a algún usuario, también lo quitamos
                users = self.env["res.users"].sudo().with_context(active_test=False).search([("groups_id", "in", [group.id])])
                users.write({"groups_id": [(3, group.id)]})

            # Limpiar cachés (igual conviene logout/login)
            try:
                self.env["ir.ui.menu"].clear_caches()
            except Exception:
                pass
            try:
                self.env["ir.ui.view"]._clear_cache()
            except Exception:
                pass

        return res
