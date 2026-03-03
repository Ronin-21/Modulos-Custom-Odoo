# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PadronCheckin(models.Model):
    _name = "padron.checkin"
    _description = "Marcación de Voto (por evento)"
    _order = "checkin_datetime desc, id desc"

    event_id = fields.Many2one("padron.event", string="Evento", required=True, index=True, ondelete="cascade")
    person_id = fields.Many2one(
        "res.partner",
        string="Persona (Padrón)",
        required=True,
        index=True,
        domain=[("is_padron_person", "=", True)],
        ondelete="cascade",
    )
    mesa_id = fields.Many2one("padron.mesa", string="Mesa N°", related="person_id.mesa_id", store=True, index=True)
    vote_status = fields.Selection(
        [
            ("voted", "Votó"),
            ("not_voted", "No votó"),
            ("absent", "Ausente"),
            ("observed", "Observado"),
        ],
        string="Estado",
        required=True,
        default="voted",
        index=True,
    )
    user_id = fields.Many2one("res.users", string="Marcado por", default=lambda self: self.env.user, required=True, index=True)
    checkin_datetime = fields.Datetime(string="Fecha/Hora", default=lambda self: fields.Datetime.now(), required=True, index=True)

    # Opcional: vincular vehículo para reportes cruzados (si se marca desde traslado o si se elige manualmente)
    vehicle_id = fields.Many2one("fleet.vehicle", string="Vehículo", index=True)

    _sql_constraints = [
        ("padron_checkin_event_person_uniq", "unique(event_id, person_id)", "Esta persona ya tiene una marcación para este evento."),
    ]

    @api.constrains("person_id")
    def _check_person_is_padron(self):
        for rec in self:
            if rec.person_id and not rec.person_id.is_padron_person:
                raise ValidationError(_("La persona seleccionada no pertenece al padrón."))
