from odoo import models, fields, api

class DiscountRule(models.Model):
    _name = 'discount.rule'
    _description = 'Reglas de Descuento por Litros'
    _order = 'min_liters asc'

    name = fields.Char(
        string="Nombre",
        compute="_compute_name",
        store=True,
        readonly=True
    )
    min_liters = fields.Float(
        string="Cantidad mínima (Litros)",
        required=True,
        help="Cantidad mínima de litros para aplicar este descuento."
    )
    discount = fields.Float(
        string="Descuento (%)",
        required=True,
        help="Porcentaje de descuento que se aplica cuando se alcanza la cantidad mínima."
    )

    _sql_constraints = [
        ("unique_min_liters", "unique(min_liters)", "Ya existe una regla con esa cantidad mínima."),
        ("check_discount_positive", "check(discount > 0)", "El descuento debe ser mayor a 0."),
        ("check_min_liters_positive", "check(min_liters > 0)", "La cantidad mínima de litros debe ser mayor a 0."),
    ]

    @api.depends('min_liters', 'discount')
    def _compute_name(self):
        for record in self:
            record.name = f"Desde {record.min_liters} L → {record.discount}%"