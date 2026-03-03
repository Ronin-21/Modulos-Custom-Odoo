# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PadronEvent(models.Model):
    _name = "padron.event"
    _description = "Evento / Jornada de Votación"
    _order = "date desc, id desc"

    name = fields.Char(string="Nombre", required=True)
    date = fields.Date(string="Fecha", required=True, default=fields.Date.context_today)
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("active", "Activo"),
            ("closed", "Cerrado"),
        ],
        string="Estado",
        default="draft",
        required=True,
        index=True,
    )

    active_event = fields.Boolean(string="Evento activo", compute="_compute_active_event", store=False)

    @api.depends("state")
    def _compute_active_event(self):
        for rec in self:
            rec.active_event = rec.state == "active"

    def action_set_active(self):
        for rec in self:
            # Cerrar otros activos
            others = self.search([("id", "!=", rec.id), ("state", "=", "active")])
            others.write({"state": "draft"})
            rec.state = "active"

    def action_close(self):
        for rec in self:
            if rec.state != "active":
                raise UserError(_("Solo se puede cerrar un evento activo."))
            rec.state = "closed"
