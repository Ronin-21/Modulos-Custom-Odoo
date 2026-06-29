# -*- coding: utf-8 -*-
"""
stock_picking.py
================
Agrega verificación de compatibilidad de ubicaciones en transferencias.

Decisión de diseño
------------------
**No se usa @api.constrains** en transferencias porque podría romper flujos
automatizados, acciones planificadas, wizard de Odoo y operaciones internas.

En su lugar se provee:
- Campo ``location_compatibility_info`` (Char, compute): muestra un aviso
  visual en el formulario si hay incompatibilidad.
- Método ``action_check_location_compatibility``: botón manual para verificar
  y ver el detalle.
- Método ``_check_location_compatibility_silent``: retorna lista de issues
  sin lanzar excepciones; usado por el wizard de diagnóstico.

La validación solo aplica si la ubicación tiene ``allowed_company_ids``
configurado. Ubicaciones técnicas siempre se permiten.
"""

import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # ------------------------------------------------------------------
    # Campo informativo (no bloquea)
    # ------------------------------------------------------------------

    location_compatibility_info = fields.Char(
        string='Compatibilidad de ubicaciones',
        compute='_compute_location_compatibility_info',
        help='Indica si las ubicaciones de esta transferencia son compatibles con la empresa.',
    )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------

    @api.depends(
        'location_id',
        'location_id.allowed_company_ids',
        'location_dest_id',
        'location_dest_id.allowed_company_ids',
        'company_id',
    )
    def _compute_location_compatibility_info(self):
        for picking in self:
            issues = picking._check_location_compatibility_silent()
            if issues:
                picking.location_compatibility_info = _(
                    '⚠ Incompatibilidad: %s'
                ) % ' | '.join(issues)
            else:
                picking.location_compatibility_info = False

    # ------------------------------------------------------------------
    # Métodos
    # ------------------------------------------------------------------

    def _check_location_compatibility_silent(self):
        """
        Verifica compatibilidad de ubicaciones con la empresa de la transferencia.

        :return: lista de strings con los problemas encontrados (puede ser vacía).
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
                    '%s "%s" [%s]' % (
                        label,
                        loc.complete_name,
                        ', '.join(loc.allowed_company_ids.mapped('name')),
                    )
                )

        return issues

    def action_check_location_compatibility(self):
        """
        Botón manual: verifica y muestra compatibilidad de ubicaciones
        sin bloquear la transferencia.
        """
        self.ensure_one()
        issues = self._check_location_compatibility_silent()

        if issues:
            msg = _(
                'Empresa "%s" no tiene permiso en las siguientes ubicaciones:\n\n%s\n\n'
                'Agregue la empresa a las "Empresas permitidas" de cada ubicación '
                'para resolver el conflicto.'
            ) % (self.company_id.name, '\n'.join('• ' + i for i in issues))
            msg_type = 'danger'
        else:
            msg = _(
                '✓ Las ubicaciones de esta transferencia son compatibles con '
                'la empresa "%s".'
            ) % (self.company_id.name if self.company_id else _('(sin empresa)'))
            msg_type = 'success'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Compatibilidad de ubicaciones'),
                'message': msg,
                'type': msg_type,
                'sticky': True,
            },
        }
