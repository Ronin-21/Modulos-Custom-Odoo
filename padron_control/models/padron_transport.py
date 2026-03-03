# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PadronTransportLine(models.Model):
    _name = "padron.transport.line"
    _description = "Control de Traslado (por evento)"
    _order = "transport_datetime desc, id desc"

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

    vehicle_id = fields.Many2one("fleet.vehicle", string="Vehículo", required=True, index=True)
    transport_status = fields.Selection(
        [
            ("assigned", "Asignado"),
            ("transported", "Transportó"),
            ("no_show", "No se presentó"),
            ("reassigned", "Reasignado"),
        ],
        string="Estado de traslado",
        required=True,
        default="assigned",
        index=True,
    )
    user_id = fields.Many2one("res.users", string="Marcado por", default=lambda self: self.env.user, required=True, index=True)
    transport_datetime = fields.Datetime(string="Fecha/Hora", default=lambda self: fields.Datetime.now(), required=True, index=True)
    note = fields.Char(string="Nota")

    _sql_constraints = [
        ("padron_transport_event_person_uniq", "unique(event_id, person_id)", "Esta persona ya tiene un control de traslado para este evento."),
    ]

    @api.constrains("person_id")
    def _check_person_is_padron(self):
        for rec in self:
            if rec.person_id and not rec.person_id.is_padron_person:
                raise ValidationError(_("La persona seleccionada no pertenece al padrón."))
