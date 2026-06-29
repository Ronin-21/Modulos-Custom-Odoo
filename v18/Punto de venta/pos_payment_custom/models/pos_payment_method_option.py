from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PosPaymentMethodAdjustmentOption(models.Model):
    _name = "pos.payment.method.adjustment.option"
    _description = "Opciones de ajuste por método de pago"
    _order = "sequence, id"

    payment_method_id = fields.Many2one(
        "pos.payment.method",
        required=True,
        ondelete="cascade",
        string="Método de pago",
    )

    name = fields.Char(string="Nombre", required=True)
    percent = fields.Float(string="Porcentaje (%)", default=0.0)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    @api.constrains("percent")
    def _check_percent(self):
        for r in self:
            if r.percent < 0 or r.percent > 100:
                raise ValidationError("El porcentaje debe estar entre 0 y 100.")
