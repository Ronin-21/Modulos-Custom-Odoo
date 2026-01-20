# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    apply_adjustment = fields.Boolean(
        string="Aplicar descuento/recargo",
        help="Permite aplicar un ajuste al usar este método de pago.",
    )

    adjustment_type = fields.Selection(
        [
            ("discount", "Descuento"),
            ("surcharge", "Recargo"),
        ],
        string="Tipo de ajuste",
        default="discount",
    )

    adjustment_product_id = fields.Many2one(
        "product.product",
        string="Producto de recargo",
        help="Producto que se agregará como línea cuando el método tenga Recargo.",
        domain=[("available_in_pos", "=", True)],
    )

    # ✅ Campos para configuración POR TARJETA
    card_ids = fields.One2many(
        "pos.payment.method.card",
        "payment_method_id",
        string="Tarjetas",
        help="Diferentes tarjetas con sus propias opciones de cuotas."
    )

    # ✅ Campo para enviar tarjetas al POS
    cards_config = fields.Json(
        string="Configuración de Tarjetas (POS)",
        compute="_compute_cards_config",
        readonly=True,
    )

    @api.depends(
        "card_ids",
        "card_ids.name",
        "card_ids.active",
        "card_ids.sequence",
        "card_ids.adjustment_options",
        "card_ids.requires_coupon",
    )
    def _compute_cards_config(self):
        for m in self:
            cards = m.card_ids.filtered(lambda c: c.active).sorted("sequence")
            m.cards_config = [
                {
                    "id": c.id,
                    "name": c.name,
                    "requires_coupon": c.requires_coupon,
                    "options": c.adjustment_options,
                }
                for c in cards
            ]

    @api.constrains(
        "apply_adjustment",
        "adjustment_type",
        "adjustment_product_id",
        "card_ids"
    )
    def _check_adjustment(self):
        for m in self:
            if not m.apply_adjustment:
                continue

            # Validaciones para RECARGO
            if m.adjustment_type == "surcharge":
                # Debe tener producto de recargo
                if not m.adjustment_product_id:
                    raise ValidationError(
                        "Si el método tiene Recargo, debe seleccionar un Producto de recargo."
                    )

                # Validar que el producto esté disponible en POS
                if not m.adjustment_product_id.available_in_pos:
                    raise ValidationError(
                        f"El producto '{m.adjustment_product_id.name}' debe estar "
                        "marcado como 'Disponible en el POS'."
                    )

                # Debe tener al menos una tarjeta
                if not m.card_ids:
                    raise ValidationError(
                        "Debe crear al menos una tarjeta con sus opciones de cuotas."
                    )

                # Cada tarjeta debe tener al menos una opción
                for card in m.card_ids:
                    if not card.adjustment_option_ids:
                        raise ValidationError(
                            f"La tarjeta '{card.name}' debe tener al menos una opción de cuotas."
                        )

    def _load_pos_data_fields(self, config_id):
        fields_list = []
        parent = super(PosPaymentMethod, self)
        if hasattr(parent, "_load_pos_data_fields"):
            fields_list = parent._load_pos_data_fields(config_id)

        extra = [
            "apply_adjustment",
            "adjustment_type",
            "adjustment_product_id",
            "cards_config",
        ]
        for f in extra:
            if f not in fields_list:
                fields_list.append(f)
        return fields_list