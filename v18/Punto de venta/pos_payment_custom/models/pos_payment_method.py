# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

# Reutilizamos el helper que YA tenés en hooks.py (así no duplicamos lógica)
from ..hooks import _get_or_create_surcharge_product


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

    discount_percent = fields.Float(
        string="Porcentaje de descuento (%)",
        default=0.0,
        help="Porcentaje fijo de descuento a aplicar cuando este método está en 'Descuento'. "
            "Ej: 10 = 10%.",
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

    @api.constrains("discount_percent")
    def _check_discount_percent(self):
        for m in self:
            if m.discount_percent < 0 or m.discount_percent > 100:
                raise ValidationError(_("El porcentaje de descuento debe estar entre 0 y 100."))

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
        # Permite que el botón funcione aunque el cliente intente “guardar” antes de ejecutar
        if self.env.context.get("ppc_skip_adjustment_check"):
            return

        for m in self:
            if not m.apply_adjustment:
                continue

            # Validaciones para RECARGO
            if m.adjustment_type == "surcharge":
                # Debe tener producto de recargo
                if not m.adjustment_product_id:
                    raise ValidationError(
                        "Si el método tiene Recargo, debe seleccionar un Producto de recargo "
                        "(o usar el botón para crearlo/traerlo)."
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

    def action_get_or_create_surcharge_product(self):
        """Botón: crea o trae el producto de recargo para la empresa del método y lo asigna."""
        self.ensure_one()

        if not self.apply_adjustment or self.adjustment_type != "surcharge":
            raise UserError(_("Este botón solo aplica cuando el método tiene ajuste en modo Recargo."))

        company = self.company_id or self.env.company

        # Crea/trae producto por compañía (helper ya existente en hooks.py)
        product = _get_or_create_surcharge_product(self.env, company)

        # Asegurar que esté disponible en POS (por si existía mal configurado)
        if "available_in_pos" in product._fields and not product.available_in_pos:
            product.sudo().write({"available_in_pos": True})

        # Asignar al método (con contexto que evita el constrain si el cliente hace pre-save)
        self.with_context(ppc_skip_adjustment_check=True).write({"adjustment_product_id": product.id})

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Producto de recargo listo"),
                "message": _("Se asignó el producto '%s' al método de pago.") % (product.display_name,),
                "type": "success",
                "sticky": False,
            },
        }

    def _load_pos_data_fields(self, config_id):
        fields_list = []
        parent = super(PosPaymentMethod, self)
        if hasattr(parent, "_load_pos_data_fields"):
            fields_list = parent._load_pos_data_fields(config_id)

        extra = [
            "apply_adjustment",
            "adjustment_type",
            "adjustment_product_id",
            "discount_percent",
            "cards_config",
        ]
        for f in extra:
            if f not in fields_list:
                fields_list.append(f)
        return fields_list