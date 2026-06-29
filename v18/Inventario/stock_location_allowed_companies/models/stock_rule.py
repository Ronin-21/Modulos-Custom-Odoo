# -*- coding: utf-8 -*-
"""
stock_rule.py
=============
Agrega validación de compatibilidad de ubicaciones en reglas push/pull/rutas.

Decisión de diseño
------------------
Ídem a ``stock_picking_type.py``: la validación solo se activa cuando la
ubicación tiene ``allowed_company_ids`` configurado. Si está vacío, no hay
restricción custom y no se bloquea nada.

Las reglas intercompañía (``propagate_company_id``) se tratan con cuidado:
si la regla no tiene empresa asignada, se omite la validación de empresa.
"""

import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockRule(models.Model):
    _inherit = 'stock.rule'

    # Campo informativo
    location_compatibility_warning = fields.Char(
        string='Aviso de compatibilidad',
        compute='_compute_location_compatibility_warning',
        help=(
            'Muestra un aviso si alguna ubicación de la regla no incluye '
            'la empresa de la regla en sus empresas permitidas.'
        ),
    )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------

    @api.depends(
        'location_src_id',
        'location_src_id.allowed_company_ids',
        'location_dest_id',
        'location_dest_id.allowed_company_ids',
        'company_id',
    )
    def _compute_location_compatibility_warning(self):
        for rule in self:
            warnings = []
            if not rule.company_id:
                rule.location_compatibility_warning = False
                continue

            for fname, label in [
                ('location_src_id', 'Origen'),
                ('location_dest_id', 'Destino'),
            ]:
                loc = rule[fname]
                if not loc or not loc.allowed_company_ids:
                    continue
                if not loc.is_allowed_for_company(rule.company_id):
                    warnings.append(
                        _('Ubicación %s (%s) no incluye la empresa "%s".')
                        % (label, loc.complete_name, rule.company_id.name)
                    )

            rule.location_compatibility_warning = ' | '.join(warnings) if warnings else False

    # ------------------------------------------------------------------
    # Constraint
    # ------------------------------------------------------------------

    @api.constrains(
        'location_src_id',
        'location_dest_id',
        'company_id',
    )
    def _check_location_company_compatibility(self):
        """
        Valida que las ubicaciones de la regla sean compatibles con su empresa,
        según ``allowed_company_ids``.

        Solo aplica cuando la ubicación tiene ``allowed_company_ids`` configurado.
        Si la regla no tiene empresa, se omite (posible regla global o intercompañía).
        """
        for rule in self:
            if not rule.company_id:
                continue

            for fname, label in [
                ('location_src_id', _('Ubicación origen')),
                ('location_dest_id', _('Ubicación destino')),
            ]:
                loc = rule[fname]
                if not loc or not loc.allowed_company_ids:
                    continue
                if loc._is_technical_location():
                    continue
                if not loc.is_allowed_for_company(rule.company_id):
                    raise UserError(_(
                        'Regla "%(rule)s" — Empresa "%(company)s":\n'
                        '%(field)s "%(loc)s" no permite esta empresa.\n\n'
                        'Empresas permitidas en esa ubicación: %(allowed)s\n\n'
                        'Corrija las empresas permitidas de la ubicación '
                        'o seleccione una ubicación compatible.'
                    ) % {
                        'rule': rule.name,
                        'company': rule.company_id.name,
                        'field': label,
                        'loc': loc.complete_name,
                        'allowed': ', '.join(loc.allowed_company_ids.mapped('name')) or '(ninguna)',
                    })

    # ------------------------------------------------------------------
    # Método de diagnóstico
    # ------------------------------------------------------------------

    def action_check_location_compatibility(self):
        """Verifica compatibilidad de ubicaciones de la regla sin bloquear."""
        self.ensure_one()
        issues = []

        if not self.company_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin empresa'),
                    'message': _('Esta regla no tiene empresa asignada.'),
                    'type': 'warning',
                    'sticky': False,
                },
            }

        for fname, label in [
            ('location_src_id', _('Origen')),
            ('location_dest_id', _('Destino')),
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
            msg = _('Incompatibilidades en "%s":\n\n%s') % (self.name, '\n'.join(issues))
            msg_type = 'danger'
        else:
            msg = _('✓ Las ubicaciones de la regla "%s" son compatibles.') % self.name
            msg_type = 'success'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Verificación'),
                'message': msg,
                'type': msg_type,
                'sticky': True,
            },
        }
