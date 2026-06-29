# -*- coding: utf-8 -*-
"""
stock_picking_type.py
=====================
Agrega validación de compatibilidad de ubicaciones en tipos de operación.

Decisión de diseño
------------------
La validación es un ``@api.constrains`` que **solo se dispara si la ubicación
tiene ``allowed_company_ids`` configurado** (campo no vacío). Si la ubicación
no tiene restricción custom, no se valida nada: comportamiento transparente.

Esto garantiza que los tipos de operación existentes sigan funcionando tal cual,
y solo se valida cuando el administrador configure explícitamente empresas
permitidas en las ubicaciones.
"""

import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    # Campo informativo: compatibilidad con allowed_company_ids
    location_compatibility_warning = fields.Char(
        string='Aviso de compatibilidad',
        compute='_compute_location_compatibility_warning',
        help=(
            'Muestra un aviso si alguna de las ubicaciones por defecto no '
            'incluye la empresa del tipo de operación en sus empresas permitidas.'
        ),
    )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------

    @api.depends(
        'default_location_src_id',
        'default_location_src_id.allowed_company_ids',
        'default_location_dest_id',
        'default_location_dest_id.allowed_company_ids',
        'company_id',
    )
    def _compute_location_compatibility_warning(self):
        for pt in self:
            warnings = []
            if not pt.company_id:
                pt.location_compatibility_warning = False
                continue

            for fname, label in [
                ('default_location_src_id', 'Origen'),
                ('default_location_dest_id', 'Destino'),
            ]:
                loc = pt[fname]
                if not loc:
                    continue
                if (
                    loc.allowed_company_ids
                    and not loc.is_allowed_for_company(pt.company_id)
                ):
                    warnings.append(
                        _('Ubicación %s (%s) no incluye la empresa "%s".')
                        % (label, loc.complete_name, pt.company_id.name)
                    )

            pt.location_compatibility_warning = ' | '.join(warnings) if warnings else False

    # ------------------------------------------------------------------
    # Constraint
    # ------------------------------------------------------------------

    @api.constrains(
        'default_location_src_id',
        'default_location_dest_id',
        'company_id',
    )
    def _check_location_company_compatibility(self):
        """
        Valida que las ubicaciones por defecto sean compatibles con la empresa
        del tipo de operación, según ``allowed_company_ids``.

        La validación **solo aplica** cuando la ubicación tiene
        ``allowed_company_ids`` configurado (no vacío). Si está vacío,
        la ubicación no tiene restricción custom y se omite la validación.
        """
        for pt in self:
            if not pt.company_id:
                continue

            for fname, label in [
                ('default_location_src_id', _('Ubicación origen por defecto')),
                ('default_location_dest_id', _('Ubicación destino por defecto')),
            ]:
                loc = pt[fname]
                if not loc:
                    continue
                # Solo validar si la ubicación tiene restricción custom
                if not loc.allowed_company_ids:
                    continue
                if loc._is_technical_location():
                    continue
                if not loc.is_allowed_for_company(pt.company_id):
                    raise UserError(_(
                        'Tipo de operación "%(op)s" — Empresa "%(company)s":\n'
                        '%(field)s "%(loc)s" no permite esta empresa.\n\n'
                        'Empresas permitidas en esa ubicación: %(allowed)s\n\n'
                        'Agregue la empresa "%(company)s" a las empresas permitidas '
                        'de la ubicación, o seleccione una ubicación compatible.'
                    ) % {
                        'op': pt.name,
                        'company': pt.company_id.name,
                        'field': label,
                        'loc': loc.complete_name,
                        'allowed': ', '.join(loc.allowed_company_ids.mapped('name')) or '(ninguna)',
                    })

    # ------------------------------------------------------------------
    # Método de diagnóstico (llamable manualmente)
    # ------------------------------------------------------------------

    def action_check_location_compatibility(self):
        """
        Acción manual para verificar compatibilidad de ubicaciones.
        Devuelve un mensaje al usuario sin bloquear ningún proceso.
        """
        self.ensure_one()
        issues = []

        if not self.company_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin empresa definida'),
                    'message': _(
                        'Este tipo de operación no tiene empresa asignada. '
                        'No es posible verificar compatibilidad.'
                    ),
                    'type': 'warning',
                    'sticky': False,
                },
            }

        for fname, label in [
            ('default_location_src_id', _('Origen')),
            ('default_location_dest_id', _('Destino')),
        ]:
            loc = self[fname]
            if not loc or not loc.allowed_company_ids or loc._is_technical_location():
                continue
            if not loc.is_allowed_for_company(self.company_id):
                issues.append(
                    '• %s "%s": empresa "%s" no está en las permitidas [%s]' % (
                        label, loc.complete_name, self.company_id.name,
                        ', '.join(loc.allowed_company_ids.mapped('name')),
                    )
                )

        if issues:
            msg = _(
                'Incompatibilidades en "%s":\n\n%s'
            ) % (self.name, '\n'.join(issues))
            msg_type = 'danger'
        else:
            msg = _('✓ Las ubicaciones de "%s" son compatibles.') % self.name
            msg_type = 'success'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Verificación de compatibilidad'),
                'message': msg,
                'type': msg_type,
                'sticky': True,
            },
        }
