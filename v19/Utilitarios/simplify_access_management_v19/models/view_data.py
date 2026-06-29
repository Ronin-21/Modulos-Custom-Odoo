from odoo import fields, models, api, _

class view_data(models.Model):
    _name = 'view.data'
    _description = "Datos de vista"

    name = fields.Char('Nombre')
    techname = fields.Char('Tech Name')


    