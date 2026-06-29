# -*- coding: utf-8 -*-
from odoo import fields, models


class PrsCardAssignWizard(models.TransientModel):
    _name = 'prs.card.assign.wizard'
    _description = 'Asignar tarjetas existentes a un procesador'

    provider_id = fields.Many2one('prs.card.provider', required=True, readonly=True)
    card_ids = fields.Many2many(
        'account.card',
        string='Tarjetas',
        domain="[('provider_id', '=', False)]",
    )

    def action_assign(self):
        self.card_ids.write({'provider_id': self.provider_id.id})
        return {'type': 'ir.actions.act_window_close'}
