from odoo import models
from odoo.osv.expression import OR


class PosConfig(models.Model):
    _inherit = "pos.config"

    def _get_available_product_domain(self):
        domain = super()._get_available_product_domain()

        # Incluir productos configurados como "Producto de recargo" en métodos de pago del POS
        product_ids = set()
        for config in self:
            methods = config.payment_method_ids.filtered(
                lambda m: m.apply_adjustment
                and m.adjustment_type == "surcharge"
                and m.adjustment_product_id
            )
            product_ids.update(methods.mapped("adjustment_product_id").ids)

        if product_ids:
            domain = OR([domain, [("id", "in", list(product_ids))]])

        return domain
