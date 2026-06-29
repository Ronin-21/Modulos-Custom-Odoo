from odoo import api, fields, models


class menu_item(models.Model):
    _name = 'menu.item'
    _description = "Elemento de menú"

    name = fields.Char('Menu')
    menu_id = fields.Integer('Menu ID')