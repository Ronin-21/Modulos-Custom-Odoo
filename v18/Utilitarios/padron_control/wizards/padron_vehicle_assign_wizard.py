# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PadronVehicleAssignWizard(models.TransientModel):
    _name = "padron.vehicle.assign.wizard"
    _description = "Asignar personas del padrón a un vehículo"

    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehículo",
        required=True,
        readonly=True,
    )

    replace_current = fields.Boolean(
        string="Reemplazar asignación actual",
        default=False,
        help=(
            "Si está marcado, se quitará este vehículo a las personas que estén "
            "actualmente asignadas antes de asignar las nuevas."
        ),
    )

    partner_ids = fields.Many2many(
        "res.partner",
        "padron_vehicle_assign_wizard_partner_rel",
        "wizard_id",
        "partner_id",
        string="Personas a asignar",
        # El campo correcto en res.partner es is_padron_person (Es del Padrón)
        domain=[("is_padron_person", "=", True)],
        help="Solo se muestran contactos marcados como 'Es del Padrón'.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get("active_model") == "fleet.vehicle" and self.env.context.get("active_id"):
            res["vehicle_id"] = self.env.context["active_id"]
        return res

    def action_apply(self):
        self.ensure_one()
        if not self.vehicle_id:
            raise UserError(_("No hay vehículo seleccionado."))

        vehicle = self.vehicle_id

        if self.replace_current:
            old_partners = self.env["res.partner"].search([("vehicle_id", "=", vehicle.id)])
            if old_partners:
                old_partners.write({"vehicle_id": False})

        if self.partner_ids:
            self.partner_ids.write({"vehicle_id": vehicle.id})

        return {"type": "ir.actions.act_window_close"}
