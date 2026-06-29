from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_update_prices_lines(self):
        """
        Excluye del recálculo masivo las líneas que tienen lista de precios individual.
        Cuando el usuario hace clic en "Actualizar Precios" (action_update_prices),
        las líneas con line_pricelist_id mantienen su precio calculado por su propia lista.
        """
        return super()._get_update_prices_lines().filtered(
            lambda line: not line.line_pricelist_id
        )
