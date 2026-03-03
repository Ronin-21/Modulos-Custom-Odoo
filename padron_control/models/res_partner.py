# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Marca general de pertenencia al padrón (para filtrar y aplicar reglas)
    is_padron_person = fields.Boolean(string="Es del Padrón", default=False, index=True)

    # Identificadores del padrón
    dni = fields.Char(string="DNI", index=True)
    tramite = fields.Char(string="N° de Trámite", index=True)

    # Asignación a mesa y vehículo (flota)
    mesa_id = fields.Many2one("padron.mesa", string="Mesa N°", index=True)
    vehicle_id = fields.Many2one("fleet.vehicle", string="Vehículo", index=True)

    # Estado de voto (simple, para operación diaria y reportes rápidos)
    padron_vote_state = fields.Selection(
        [
            ("not_voted", "No votó"),
            ("voted", "Votó"),
        ],
        string="Estado de voto",
        default="not_voted",
        index=True,
        tracking=False,
    )
    padron_vote_datetime = fields.Datetime(string="Fecha/Hora voto", index=True)
    padron_vote_user_id = fields.Many2one("res.users", string="Marcado por", index=True)

    def _padron_assert_user_mesa_access(self):
        """Bloqueo de seguridad adicional (además de reglas de registro).
        Si el usuario tiene mesas asignadas, solo puede operar personas de esas mesas,
        excepto si es Supervisor/Admin de padrón.
        """
        user = self.env.user
        if user.has_group("padron_control.group_padron_admin") or user.has_group("padron_control.group_padron_supervisor"):
            return
        mesa_ids = user.mesa_ids.ids
        if not mesa_ids:
            return
        for partner in self:
            if partner.mesa_id and partner.mesa_id.id not in mesa_ids:
                raise UserError(_("No tiene permisos para operar la mesa %s.") % (partner.mesa_id.name or partner.mesa_id.numero or partner.mesa_id.id))

    def action_mark_voted(self):
        """Marca como 'Votó' y deja trazabilidad básica.
        Además, si existe un 'Evento' activo (padron.event), crea/actualiza el checkin.
        """
        now = fields.Datetime.now()
        self._padron_assert_user_mesa_access()

        # Evento activo (opcional)
        active_event = self.env["padron.event"].search([("state", "=", "active")], limit=1)
        Checkin = self.env["padron.checkin"]

        for partner in self:
            if not partner.is_padron_person:
                continue
            if partner.padron_vote_state == "voted":
                continue

            partner.write(
                {
                    "padron_vote_state": "voted",
                    "padron_vote_datetime": now,
                    "padron_vote_user_id": self.env.user.id,
                }
            )

            # Historial (si hay evento activo)
            if active_event:
                existing = Checkin.search(
                    [("event_id", "=", active_event.id), ("person_id", "=", partner.id)],
                    limit=1,
                )
                vals = {
                    "event_id": active_event.id,
                    "person_id": partner.id,
                    "vehicle_id": partner.vehicle_id.id,
                    "vote_status": "voted",
                    "checkin_datetime": now,
                                    "user_id": self.env.user.id,
}
                if existing:
                    existing.write(vals)
                else:
                    Checkin.create(vals)

        return True

    def action_unmark_voted(self):
        """(Opcional) Desmarca el voto en el contacto. No borra el histórico."""
        self._padron_assert_user_mesa_access()
        for partner in self:
            if not partner.is_padron_person:
                continue
            partner.write(
                {
                    "padron_vote_state": "not_voted",
                    "padron_vote_datetime": False,
                    "padron_vote_user_id": False,
                }
            )
        return True

    def action_unassign_vehicle(self):
        """Quita la asignación de vehículo desde la vista del vehículo."""
        for partner in self:
            partner.vehicle_id = False
        return True
