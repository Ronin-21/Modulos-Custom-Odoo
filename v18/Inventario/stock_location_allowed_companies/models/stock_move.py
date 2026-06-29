# -*- coding: utf-8 -*-
"""
stock_move.py
=============
Métodos auxiliares de compatibilidad en movimientos de stock.

Decisión de diseño
------------------
**No se agregan constraints** en movimientos. Los movimientos son creados
por procesos automatizados (wizard, planificador, reabastecimiento, etc.)
y un constraint duro rompería la operativa.

Se provee:
- ``_check_location_compatibility_silent()``: retorna lista de issues sin
  lanzar excepciones; usado por wizard de diagnóstico.
- ``location_compatibility_warning``: campo compute para uso en la vista
  si se quiere mostrar el aviso.
"""

import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = 'stock.move'

    location_compatibility_warning = fields.Char(
        string='Aviso de compatibilidad',
        compute='_compute_location_compatibility_warning',
        help='Indica si las ubicaciones del movimiento son compatibles con la empresa.',
    )

    @api.depends(
        'location_id',
        'location_id.allowed_company_ids',
        'location_dest_id',
        'location_dest_id.allowed_company_ids',
        'company_id',
    )
    def _compute_location_compatibility_warning(self):
        for move in self:
            issues = move._check_location_compatibility_silent()
            move.location_compatibility_warning = (
                _('; ').join(issues) if issues else False
            )

    def _check_location_compatibility_silent(self):
        """
        :return: lista de strings con los problemas encontrados.
        No lanza excepciones.
        """
        self.ensure_one()
        issues = []

        if not self.company_id:
            return issues

        for fname, label in [
            ('location_id', _('Origen')),
            ('location_dest_id', _('Destino')),
        ]:
            loc = self[fname]
            if not loc or not loc.allowed_company_ids:
                continue
            if loc._is_technical_location():
                continue
            if not loc.is_allowed_for_company(self.company_id):
                issues.append(
                    '%s: "%s" no permite empresa "%s"' % (
                        label, loc.complete_name, self.company_id.name,
                    )
                )

        return issues
