from odoo import fields, models


class MrpBom(models.Model):
    _inherit = "mrp.bom"

    enforce_workorder_dependency = fields.Boolean(
        string="Controlar dependencias entre operaciones",
        help="Si está activado, las órdenes de trabajo no podrán iniciarse hasta que se completen todas las operaciones de las que dependen.",
        default=False,
    )
