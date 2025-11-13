from odoo import models, fields, tools

class SaleReport(models.Model):
    _inherit = "sale.report"

    # Nuevo campo: Total de Litros
    x_total_units = fields.Float(
        string="Total de Litros",
        readonly=True,
    )

    def _select_additional_fields(self):
        """Agregar el campo x_total_units a la selección SQL"""
        res = super()._select_additional_fields()
        res["x_total_units"] = "s.x_total_units"
        return res

    def _from_additional_tables(self):
        """Asegurar que la tabla sale_order esté correctamente unida"""
        return super()._from_additional_tables()

    def _group_by_additional_fields(self):
        """Asegurar que el campo esté incluido en el GROUP BY"""
        res = super()._group_by_additional_fields()
        res.append("s.x_total_units")
        return res
