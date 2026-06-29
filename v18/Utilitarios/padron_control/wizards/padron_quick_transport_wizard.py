# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PadronQuickTransportWizard(models.TransientModel):
    _name = "padron.quick.transport.wizard"
    _description = "Marcación rápida de traslado"

    event_id = fields.Many2one("padron.event", string="Evento", required=True, default=lambda self: self._default_event())
    identifier = fields.Char(string="DNI o Trámite", required=True)
    person_id = fields.Many2one("res.partner", string="Persona", readonly=True)
    mesa_id = fields.Many2one("padron.mesa", string="Mesa N°", readonly=True)

    vehicle_id = fields.Many2one("fleet.vehicle", string="Vehículo", required=True)
    transport_status = fields.Selection(
        [
            ("assigned", "Asignado"),
            ("transported", "Transportó"),
            ("no_show", "No se presentó"),
            ("reassigned", "Reasignado"),
        ],
        string="Estado",
        required=True,
        default="transported",
    )
    note = fields.Char(string="Nota")

    @api.model
    def _default_event(self):
        active = self.env["padron.event"].search([("state", "=", "active")], limit=1)
        return active.id or False

    @api.onchange("identifier", "event_id")
    def _onchange_identifier(self):
        self.person_id = False
        self.mesa_id = False
        ident = (self.identifier or "").strip()
        if not ident:
            return

        mesa_ids = self.env.user.mesa_ids.ids
        domain_base = [("is_padron_person", "=", True)]
        if mesa_ids:
            domain_base += [("mesa_id", "in", mesa_ids)]
        else:
            raise UserError(_("Tu usuario no tiene Mesas asignadas. Contactá a un administrador."))

        partners = self.env["res.partner"].search(domain_base + ["|", ("dni", "=", ident), ("tramite", "=", ident)], limit=2)
        if not partners:
            raise UserError(_("No se encontró una persona del padrón para ese DNI/Trámite dentro de tus mesas."))
        if len(partners) > 1:
            raise UserError(_("Se encontró más de una persona con ese identificador. Revisá DNI/Trámite."))

        self.person_id = partners.id
        self.mesa_id = partners.mesa_id.id

    def action_mark(self):
        self.ensure_one()
        if not self.person_id:
            raise UserError(_("No hay persona seleccionada para marcar."))

        Line = self.env["padron.transport.line"]
        existing = Line.search([("event_id", "=", self.event_id.id), ("person_id", "=", self.person_id.id)], limit=1)
        vals = {
            "event_id": self.event_id.id,
            "person_id": self.person_id.id,
            "vehicle_id": self.vehicle_id.id,
            "transport_status": self.transport_status,
            "user_id": self.env.user.id,
            "transport_datetime": fields.Datetime.now(),
            "note": self.note or False,
        }
        if existing:
            existing.write(vals)
        else:
            Line.create(vals)

        self.identifier = ""
        self.person_id = False
        self.mesa_id = False
        self.note = False

        return {
            "type": "ir.actions.act_window",
            "res_model": "padron.quick.transport.wizard",
            "view_mode": "form",
            "target": "new",
            "context": dict(self.env.context, default_event_id=self.event_id.id),
        }
