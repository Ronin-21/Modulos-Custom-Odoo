from odoo import fields, models, api, _


class action_data(models.Model):
    _name = 'action.data'
    _description = "Datos de acción"

    name = fields.Char('Nombre')
    action_id = fields.Many2one('ir.actions.actions', 'Acción')
