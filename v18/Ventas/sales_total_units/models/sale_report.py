from odoo import models, fields

class SaleReport(models.Model):
    _inherit = "sale.report"

    # Total de Litros por línea
    x_total_units = fields.Float(
        string="Total de Litros",
        readonly=True,
    )

    def _select_additional_fields(self):
        """Agregar litros por línea usando SUM para evitar problemas de GROUP BY"""
        res = super()._select_additional_fields()
        # Usar SUM porque es un agregado
        res["x_total_units"] = "SUM(l.line_total_units)"
        return res