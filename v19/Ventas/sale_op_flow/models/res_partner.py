# -*- coding: utf-8 -*-
from odoo import api, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def web_name_search(self, name, specification, domain=None, operator='ilike', limit=100):
        configured = self._get_partner_search_limit()
        if configured > 0 and (limit is None or limit > configured):
            limit = configured
        return super().web_name_search(
            name=name, specification=specification,
            domain=domain, operator=operator, limit=limit,
        )

    @api.model
    def _get_partner_search_limit(self):
        try:
            return int(self.env['ir.config_parameter'].sudo().get_param(
                'sale_op_flow.partner_search_limit', '0') or 0)
        except (ValueError, TypeError):
            return 0

    @api.model
    def autocomplete_by_name(self, query, query_country_id, timeout=15):
        if not self._sof_partner_autocomplete_enabled():
            return []
        return super().autocomplete_by_name(query, query_country_id, timeout=timeout)

    @api.model
    def autocomplete_by_vat(self, vat, query_country_id, timeout=15):
        if not self._sof_partner_autocomplete_enabled():
            return []
        return super().autocomplete_by_vat(vat, query_country_id, timeout=timeout)

    @api.model
    def _sof_partner_autocomplete_enabled(self):
        try:
            raw = self.env['ir.config_parameter'].sudo().get_param(
                'sale_op_flow.partner_autocomplete_enabled', '0')
            return str(raw).lower() in ('1', 'true', 't', 'yes', 'y', 'on', 'si', 'sí')
        except Exception:
            return False
