# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    padron_person_ids = fields.One2many(
        comodel_name="res.partner",
        inverse_name="vehicle_id",
        string="Personas del Padrón",
        domain=[("is_padron_person", "=", True)],
    )

    padron_person_count = fields.Integer(string="Asignados", compute="_compute_padron_counts")
    padron_voted_count = fields.Integer(string="Votaron", compute="_compute_padron_counts")
    padron_not_voted_count = fields.Integer(string="Faltan", compute="_compute_padron_counts")
    padron_pending_count = fields.Integer(string="Pendientes", compute="_compute_padron_counts")
    padron_all_voted = fields.Boolean(string="Todos votaron", compute="_compute_padron_counts")

    @api.depends("padron_person_ids", "padron_person_ids.padron_vote_state")
    def _compute_padron_counts(self):
        for vehicle in self:
            persons = vehicle.padron_person_ids
            vehicle.padron_person_count = len(persons)
            voted = persons.filtered(lambda p: p.padron_vote_state == 'voted')
            vehicle.padron_voted_count = len(voted)
            pending = len(persons) - len(voted)
            vehicle.padron_not_voted_count = pending
            # Alias usado por las vistas del control de traslado
            vehicle.padron_pending_count = pending
            vehicle.padron_all_voted = bool(persons) and pending == 0

    def action_open_padron_persons(self):
        """Abre el listado de personas del padrón asignadas a este vehículo."""
        self.ensure_one()
        return self._action_open_padron_persons()

    def _action_open_padron_persons(self, extra_domain=None):
        self.ensure_one()
        domain = [("is_padron_person", "=", True), ("vehicle_id", "=", self.id)]
        if extra_domain:
            domain += extra_domain

        action = {
            "type": "ir.actions.act_window",
            "name": _("Personas del Padrón"),
            "res_model": "res.partner",
            "view_mode": "list,form",
            "domain": domain,
            "context": {
                "search_default_is_padron_person": 1,
                "default_is_padron_person": True,
                "default_vehicle_id": self.id,
            },
        }
        # Preferir la vista de padrón si existe
        try:
            list_view = self.env.ref("padron_control.view_partner_tree_padron")
            action["views"] = [(list_view.id, "list"), (False, "form")]
        except Exception:
            pass
        return action

    def action_view_padron_persons(self):
        return self._action_open_padron_persons()

    def action_view_padron_persons_voted(self):
        return self._action_open_padron_persons([("padron_vote_state", "=", "voted")])

    def action_view_padron_persons_not_voted(self):
        return self._action_open_padron_persons([("padron_vote_state", "=", "not_voted")])


    def action_open_padron_voted_persons(self):
        """Abre las personas asignadas que ya votaron."""
        return self._action_open_padron_persons([('padron_vote_state', '=', 'voted')])

    def action_open_padron_pending_persons(self):
        """Abre las personas asignadas pendientes de voto."""
        return self._action_open_padron_persons([('padron_vote_state', '=', 'not_voted')])

    def action_open_padron_assign_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asignar personas al vehículo',
            'res_model': 'padron.vehicle.assign.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_vehicle_id': self.id,
            },
        }
