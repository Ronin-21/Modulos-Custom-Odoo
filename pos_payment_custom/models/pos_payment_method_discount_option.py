# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PosPaymentMethodDiscountOption(models.Model):
    _name = "pos.payment.method.discount.option"
    _description = "Opciones de descuento por método de pago"
    _order = "sequence, percent desc, id"

    payment_method_id = fields.Many2one(
        "pos.payment.method",
        required=True,
        ondelete="cascade",
        string="Método de pago",
    )

    name = fields.Char(
        string="Nombre",
        compute="_compute_name",
        store=True,
        readonly=False,
    )

    percent = fields.Float(
        string="Porcentaje de Descuento (%)",
        default=0.0,
        required=True,
        help="Porcentaje de descuento (ej: 10 para 10% de descuento)"
    )

    active = fields.Boolean(
        default=True
    )

    sequence = fields.Integer(
        default=10
    )

    @api.depends("percent")
    def _compute_name(self):
        for opt in self:
            # Solo auto-generar si está vacío
            if not opt.name:
                opt.name = f"{opt.percent}% de descuento"

    @api.constrains("percent")
    def _check_percent(self):
        for opt in self:
            if opt.percent < 0 or opt.percent > 100:
                raise ValidationError("El porcentaje debe estar entre 0 y 100.")