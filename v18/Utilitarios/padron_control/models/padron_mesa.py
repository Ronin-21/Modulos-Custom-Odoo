# -*- coding: utf-8 -*-
from odoo import models, fields, api


class PadronMesa(models.Model):
    _name = "padron.mesa"
    _description = "Mesa (Padrón)"
    _rec_name = "number"
    _order = "number"

    number = fields.Char(string="Mesa N°", required=True, index=True)
    name = fields.Char(string="Descripción", compute="_compute_name", store=True)
    zone = fields.Char(string="Zona / Circuito")

    _sql_constraints = [
        ("padron_mesa_number_uniq", "unique(number)", "La Mesa N° debe ser única."),
    ]
    @api.depends("number")
    def _compute_name(self):
        for rec in self:
            rec.name = rec.number
