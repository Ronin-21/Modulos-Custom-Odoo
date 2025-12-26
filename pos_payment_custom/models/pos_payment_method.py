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

    adjustment_value = fields.Float(
        string="Porcentaje (%)",
        help="Porcentaje (0-100). Para recargos con opciones, este valor puede usarse como default si no hay opciones.",
        default=0.0,
    )

    adjustment_product_id = fields.Many2one(
        "product.product",
        string="Producto de recargo",
        help="Producto (idealmente Servicio) que se agregará como línea cuando el método tenga Recargo.",
        domain=[("available_in_pos", "=", True)],
    )

    adjustment_option_ids = fields.One2many(
        "pos.payment.method.adjustment.option",
        "payment_method_id",
        string="Opciones de recargo",
        help="Opciones de recargo (ej: Visa 3 cuotas 15%).",
    )

    # Esto viaja al POS sin tener que cargar otro modelo:
    adjustment_options = fields.Json(
        string="Opciones (POS)",
        compute="_compute_adjustment_options",
        readonly=True,
    )

    @api.depends("adjustment_option_ids", "adjustment_option_ids.name", "adjustment_option_ids.percent",
                 "adjustment_option_ids.active", "adjustment_option_ids.sequence")
    def _compute_adjustment_options(self):
        for m in self:
            opts = m.adjustment_option_ids.filtered(lambda o: o.active).sorted("sequence")
            m.adjustment_options = [
                {"id": o.id, "name": o.name, "percent": o.percent}
                for o in opts
            ]

    @api.constrains("apply_adjustment", "adjustment_type", "adjustment_value", "adjustment_product_id")
    def _check_adjustment(self):
        for m in self:
            if not m.apply_adjustment:
                continue

            if m.adjustment_value < 0 or m.adjustment_value > 100:
                raise ValidationError("El porcentaje debe estar entre 0 y 100.")

            # Si es recargo, debe haber producto de recargo
            if m.adjustment_type == "surcharge" and not m.adjustment_product_id:
                raise ValidationError("Si el método tiene Recargo, debe seleccionar un Producto de recargo.")

    def _load_pos_data_fields(self, config_id):
        fields_list = []
        parent = super(PosPaymentMethod, self)
        if hasattr(parent, "_load_pos_data_fields"):
            fields_list = parent._load_pos_data_fields(config_id)

        extra = [
            "apply_adjustment",
            "adjustment_type",
            "adjustment_value",
            "adjustment_product_id",
            "adjustment_options",
        ]
        for f in extra:
            if f not in fields_list:
                fields_list.append(f)
        return fields_list
