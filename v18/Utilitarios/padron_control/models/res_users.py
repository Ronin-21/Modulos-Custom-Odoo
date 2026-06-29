# -*- coding: utf-8 -*-
from odoo import models, fields


class ResUsers(models.Model):
    _inherit = "res.users"

    mesa_ids = fields.Many2many(
        "padron.mesa",
        "padron_mesa_user_rel",
        "user_id",
        "mesa_id",
        string="Mesas asignadas",
        help="El usuario solo podrá ver y marcar personas del padrón pertenecientes a estas mesas.",
    )
