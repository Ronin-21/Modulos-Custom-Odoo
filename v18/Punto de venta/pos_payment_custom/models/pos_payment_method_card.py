# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PosPaymentMethodCard(models.Model):
    _name = "pos.payment.method.card"
    _description = "Tarjetas de pago con cuotas"
    _order = "sequence, name"

    payment_method_id = fields.Many2one(
        "pos.payment.method",
        required=True,
        ondelete="cascade",
        string="Método de pago",
    )

    name = fields.Char(
        string="Nombre de tarjeta",
        required=True,
        help="Ejemplo: Visa, Mastercard, Naranja, etc."
    )

    sequence = fields.Integer(
        default=10,
        help="Orden de visualización"
    )

    active = fields.Boolean(
        default=True
    )

    requires_coupon = fields.Boolean(
        string="Requiere número de cupón",
        default=True,
        help="Si está marcado, será obligatorio ingresar un número de cupón para esta tarjeta."
    )

    # ✅ REMOVIDO: coupon_format - usaremos siempre 123-1234

    adjustment_option_ids = fields.One2many(
        "pos.payment.method.card.option",
        "card_id",
        string="Opciones de cuotas",
        help="Opciones de cuotas para esta tarjeta (ej: 1 Pago 0%, 3 Cuotas 15%)"
    )

    # Campo computed para enviar al POS
    adjustment_options = fields.Json(
        string="Opciones (POS)",
        compute="_compute_adjustment_options",
        readonly=True,
    )

    @api.depends(
        "adjustment_option_ids",
        "adjustment_option_ids.name",
        "adjustment_option_ids.percent",
        "adjustment_option_ids.active",
        "adjustment_option_ids.sequence"
    )
    def _compute_adjustment_options(self):
        for card in self:
            opts = card.adjustment_option_ids.filtered(lambda o: o.active).sorted("sequence")
            card.adjustment_options = [
                {
                    "id": o.id,
                    "name": o.name,
                    "percent": o.percent,
                    "installments": o.installments,
                }
                for o in opts
            ]

    @api.constrains("adjustment_option_ids")
    def _check_adjustment_options(self):
        for card in self:
            for opt in card.adjustment_option_ids:
                if opt.percent < 0 or opt.percent > 100:
                    raise ValidationError(
                        f"La opción '{opt.name}' de la tarjeta '{card.name}' tiene un porcentaje inválido. "
                        "Debe estar entre 0 y 100."
                    )


class PosPaymentMethodCardOption(models.Model):
    _name = "pos.payment.method.card.option"
    _description = "Opciones de cuotas por tarjeta"
    _order = "sequence, installments, id"

    card_id = fields.Many2one(
        "pos.payment.method.card",
        required=True,
        ondelete="cascade",
        string="Tarjeta",
    )

    name = fields.Char(
        string="Nombre",
        compute="_compute_name",
        store=True,
        readonly=False,
    )

    installments = fields.Integer(
        string="Cuotas",
        default=1,
        required=True,
        help="Número de cuotas (1 = pago único)"
    )

    percent = fields.Float(
        string="Porcentaje (%)",
        default=0.0,
        help="Recargo por esta opción de cuotas"
    )

    active = fields.Boolean(
        default=True
    )

    sequence = fields.Integer(
        default=10
    )

    @api.depends("installments", "percent")
    def _compute_name(self):
        for opt in self:
            # ✅ CAMBIO: Permitir editar el nombre manualmente
            # Solo auto-generar si está vacío
            if not opt.name:
                if opt.installments == 1:
                    opt.name = f"1 Pago ({opt.percent}%)"
                else:
                    opt.name = f"{opt.installments} Cuotas ({opt.percent}%)"

    @api.constrains("percent")
    def _check_percent(self):
        for opt in self:
            if opt.percent < 0 or opt.percent > 100:
                raise ValidationError("El porcentaje debe estar entre 0 y 100.")

    @api.constrains("installments")
    def _check_installments(self):
        for opt in self:
            if opt.installments < 1:
                raise ValidationError("El número de cuotas debe ser al menos 1.")