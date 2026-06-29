# -*- coding: utf-8 -*-
"""
stock_quant.py
==============
Agrega una acción de Ajuste de Inventario filtrada por empresas permitidas.

Decisión de diseño
------------------
**NO** se sobreescribe ``_search()`` ni ningún método de bajo nivel de
``stock.quant`` (un intento anterior causó el error
``BaseModel._search() got an unexpected keyword argument 'access_rights_uid'``).

En su lugar se provee:
- ``action_stock_inventory_allowed()``: retorna la acción de ajuste de
  inventario con un dominio dinámico que filtra por:
  * ``location_id.usage == 'internal'``
  * ``location_id.allowed_company_ids`` vacío O intersecta con las empresas
    activas del usuario.
  Esta acción se expone en el menú como "Ajuste de Inventario (Filtrado)".
  La acción original de Odoo se deja intacta.

- ``_get_inventory_location_domain()``: retorna los ids de ubicaciones
  internas permitidas para el usuario actual.
"""

import logging
from odoo import models, api, _

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    @api.model
    def _get_inventory_location_domain(self):
        """
        Retorna el dominio de quants filtrado por ubicaciones internas
        compatibles con las empresas activas del usuario.

        Lógica:
        - usage == 'internal'
        - allowed_company_ids vacío (sin restricción) O intersecta con
          las empresas activas/seleccionadas del usuario.
        """
        company_ids = self.env.companies.ids
        if not company_ids:
            return [('location_id.usage', '=', 'internal')]

        # Ubicaciones internas que son accesibles para las empresas activas
        allowed_locs = self.env['stock.location'].sudo().search([
            ('usage', '=', 'internal'),
            '|',
            ('allowed_company_ids', '=', False),
            ('allowed_company_ids', 'in', company_ids),
        ])

        return [
            ('location_id', 'in', allowed_locs.ids),
        ]

    @api.model
    def action_stock_inventory_allowed(self):
        """
        Devuelve la acción de Ajuste de Inventario filtrada por las empresas
        permitidas del usuario actual.

        Intenta reutilizar la acción base de Odoo (``stock.action_stock_inventory``)
        para heredar su vista, contexto y demás configuración, y solo reemplaza
        el dominio.
        """
        # Intentar obtener la acción base de Odoo
        try:
            action = (
                self.env.ref('stock.action_stock_inventory')
                .sudo()
                .read(['name', 'type', 'res_model', 'view_mode',
                       'view_id', 'views', 'context', 'domain',
                       'help', 'target', 'flags'])[0]
            )
            # Limpiar el id para que no sea un update de la acción existente
            action.pop('id', None)
            action.pop('xmlid', None)
        except Exception:
            _logger.warning(
                'stock_location_allowed_companies: no se pudo leer '
                'stock.action_stock_inventory; creando acción mínima.'
            )
            action = {
                'name': _('Ajuste de Inventario'),
                'type': 'ir.actions.act_window',
                'res_model': 'stock.quant',
                'view_mode': 'list,form',
                'target': 'main',
                'context': {},
            }

        # Aplicar dominio filtrado
        domain = self._get_inventory_location_domain()
        action['domain'] = domain

        # Enriquecer el nombre para que sea claro
        base_name = action.get('name') or _('Ajuste de Inventario')
        action['name'] = _('%s (Filtrado)') % base_name

        # Forzar contexto de inventario si no viene de la acción base
        ctx = dict(action.get('context') or {})
        ctx.setdefault('default_inventory_mode', True)
        action['context'] = ctx

        return action
