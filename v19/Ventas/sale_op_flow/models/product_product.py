# -*- coding: utf-8 -*-
from odoo import api, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def web_name_search(self, name, specification, domain=None, operator='ilike', limit=100):
        configured = self._get_product_search_limit()
        if configured > 0 and (limit is None or limit > configured):
            limit = configured
        return super().web_name_search(
            name=name, specification=specification,
            domain=domain, operator=operator, limit=limit,
        )

    @api.model
    def _get_product_search_limit(self):
        try:
            return int(self.env['ir.config_parameter'].sudo().get_param(
                'sale_op_flow.product_search_limit', '0') or 0)
        except (ValueError, TypeError):
            return 0
