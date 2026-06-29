# -*- coding: utf-8 -*-
"""
stock_location_diagnostic_wizard.py
=====================================
Wizard de diagnóstico de incompatibilidades entre ubicaciones y empresas.

Secciones del diagnóstico
--------------------------
1. Ubicaciones sin ``allowed_company_ids`` (no técnicas).
2. Ubicaciones compartidas usadas por tipos de operación.
3. Ubicaciones compartidas usadas por reglas push/pull.
4. Quants en ubicaciones cuya empresa no está en ``allowed_company_ids``.
5. Transferencias abiertas con ubicaciones incompatibles.

El wizard es 100% de solo lectura: no modifica ningún dato.
"""

import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

_SKIP_USAGES_DIAG = frozenset(['customer', 'supplier', 'inventory', 'production', 'view'])


class StockLocationDiagnosticWizard(models.TransientModel):
    _name = 'stock.location.diagnostic.wizard'
    _description = 'Diagnóstico de Empresas Permitidas en Ubicaciones'

    # ------------------------------------------------------------------
    # Resumen general
    # ------------------------------------------------------------------

    summary = fields.Text(
        string='Resumen',
        readonly=True,
        default=_('Haga clic en "Ejecutar diagnóstico" para analizar el entorno.'),
    )

    # ------------------------------------------------------------------
    # Sección 1: ubicaciones sin allowed_company_ids
    # ------------------------------------------------------------------

    loc_no_allowed_count = fields.Integer(
        string='Ubicaciones sin empresas permitidas',
        readonly=True,
    )
    loc_no_allowed_text = fields.Text(
        string='Detalle',
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Sección 2: tipos de operación con ubicaciones compartidas
    # ------------------------------------------------------------------

    picking_type_issue_count = fields.Integer(
        string='Tipos de operación con ubicaciones compartidas',
        readonly=True,
    )
    picking_type_issue_text = fields.Text(
        string='Detalle',
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Sección 3: reglas con ubicaciones compartidas
    # ------------------------------------------------------------------

    rule_issue_count = fields.Integer(
        string='Reglas con ubicaciones compartidas',
        readonly=True,
    )
    rule_issue_text = fields.Text(
        string='Detalle',
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Sección 4: quants en ubicaciones incompatibles
    # ------------------------------------------------------------------

    quant_issue_count = fields.Integer(
        string='Quants en ubicaciones incompatibles',
        readonly=True,
    )
    quant_issue_text = fields.Text(
        string='Detalle',
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Sección 5: pickings abiertos con ubicaciones incompatibles
    # ------------------------------------------------------------------

    picking_issue_count = fields.Integer(
        string='Transferencias abiertas con ubicaciones incompatibles',
        readonly=True,
    )
    picking_issue_text = fields.Text(
        string='Detalle',
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Acción principal
    # ------------------------------------------------------------------

    def action_run_diagnostic(self):
        """Ejecuta el diagnóstico completo y actualiza los campos."""
        self.ensure_one()

        s1_count, s1_text = self._diag_locations_no_allowed()
        s2_count, s2_text = self._diag_picking_types()
        s3_count, s3_text = self._diag_rules()
        s4_count, s4_text = self._diag_quants()
        s5_count, s5_text = self._diag_pickings()

        total_issues = s1_count + s2_count + s3_count + s4_count + s5_count

        summary_lines = [
            _('=== DIAGNÓSTICO DE EMPRESAS PERMITIDAS ===\n'),
            _('1. Ubicaciones sin empresas permitidas:  %d') % s1_count,
            _('2. Tipos de operación con ub. compartidas: %d') % s2_count,
            _('3. Reglas con ubicaciones compartidas:   %d') % s3_count,
            _('4. Quants en ubicaciones incompatibles:  %d') % s4_count,
            _('5. Transferencias abiertas incompatibles: %d') % s5_count,
            '',
            _('TOTAL de situaciones a revisar: %d') % total_issues,
        ]
        if total_issues == 0:
            summary_lines.append(_('\n✓ No se detectaron incompatibilidades.'))

        self.write({
            'summary': '\n'.join(summary_lines),
            'loc_no_allowed_count': s1_count,
            'loc_no_allowed_text': s1_text,
            'picking_type_issue_count': s2_count,
            'picking_type_issue_text': s2_text,
            'rule_issue_count': s3_count,
            'rule_issue_text': s3_text,
            'quant_issue_count': s4_count,
            'quant_issue_text': s4_text,
            'picking_issue_count': s5_count,
            'picking_issue_text': s5_text,
        })

        # Reabrir el wizard con los resultados
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_init_wizard(self):
        """Acceso directo al wizard de inicialización."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Inicializar Empresas Permitidas'),
            'res_model': 'stock.location.init.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Secciones de diagnóstico
    # ------------------------------------------------------------------

    def _diag_locations_no_allowed(self):
        """S1: ubicaciones sin allowed_company_ids (no técnicas, no skip)."""
        # return_location fue eliminado en Odoo 18; solo excluimos scrap_location
        locations = self.env['stock.location'].sudo().search([
            ('usage', 'not in', list(_SKIP_USAGES_DIAG)),
            ('scrap_location', '=', False),
            ('allowed_company_ids', '=', False),
        ])

        if not locations:
            return 0, _('(ninguna ubicación sin empresas permitidas)')

        lines = []
        for loc in locations:
            company_info = loc.company_id.name if loc.company_id else _('(sin empresa)')
            lines.append(
                '  [%s] %s  |  Empresa: %s  |  Tipo: %s'
                % (loc.id, loc.complete_name, company_info, loc.usage)
            )

        return len(locations), '\n'.join(lines)

    def _diag_picking_types(self):
        """S2: tipos de operación con ubicaciones compartidas o sin empresas permitidas."""
        shared_locs = self.env['stock.location'].sudo().search([
            ('is_shared_location', '=', True),
        ])
        all_locs_no_allowed = self.env['stock.location'].sudo().search([
            ('usage', 'not in', list(_SKIP_USAGES_DIAG)),
            ('allowed_company_ids', '=', False),
            ('company_id', '=', False),
        ])
        target_locs = shared_locs | all_locs_no_allowed

        if not target_locs:
            return 0, _('(ningún tipo de operación con ubicaciones compartidas)')

        picking_types = self.env['stock.picking.type'].sudo().search([
            '|',
            ('default_location_src_id', 'in', target_locs.ids),
            ('default_location_dest_id', 'in', target_locs.ids),
        ])

        if not picking_types:
            return 0, _('(ningún tipo de operación usa ubicaciones compartidas sin restricción)')

        lines = []
        for pt in picking_types:
            src_info = '%s [compartida=%s]' % (
                pt.default_location_src_id.complete_name if pt.default_location_src_id else '—',
                '✓' if pt.default_location_src_id in target_locs else '✗',
            )
            dest_info = '%s [compartida=%s]' % (
                pt.default_location_dest_id.complete_name if pt.default_location_dest_id else '—',
                '✓' if pt.default_location_dest_id in target_locs else '✗',
            )
            company = pt.company_id.name if pt.company_id else '(sin empresa)'
            lines.append(
                '  "%s" (empresa: %s)\n'
                '      Origen:  %s\n'
                '      Destino: %s'
                % (pt.name, company, src_info, dest_info)
            )

        return len(picking_types), '\n'.join(lines)

    def _diag_rules(self):
        """S3: reglas push/pull con ubicaciones compartidas."""
        shared_locs = self.env['stock.location'].sudo().search([
            ('is_shared_location', '=', True),
        ])
        all_locs_no_allowed = self.env['stock.location'].sudo().search([
            ('usage', 'not in', list(_SKIP_USAGES_DIAG)),
            ('allowed_company_ids', '=', False),
            ('company_id', '=', False),
        ])
        target_locs = shared_locs | all_locs_no_allowed

        if not target_locs:
            return 0, _('(ninguna regla con ubicaciones compartidas)')

        rules = self.env['stock.rule'].sudo().search([
            '|',
            ('location_src_id', 'in', target_locs.ids),
            ('location_dest_id', 'in', target_locs.ids),
        ])

        if not rules:
            return 0, _('(ninguna regla usa ubicaciones compartidas sin restricción)')

        lines = []
        for rule in rules:
            src_info = rule.location_src_id.complete_name if rule.location_src_id else '—'
            dest_info = rule.location_dest_id.complete_name if rule.location_dest_id else '—'
            route = rule.route_id.name if rule.route_id else '(sin ruta)'
            company = rule.company_id.name if rule.company_id else '(sin empresa)'
            lines.append(
                '  "%s" / Ruta: %s / Empresa: %s\n'
                '      Origen:  %s\n'
                '      Destino: %s'
                % (rule.name, route, company, src_info, dest_info)
            )

        return len(rules), '\n'.join(lines)

    def _diag_quants(self):
        """S4: quants en ubicaciones donde la empresa del quant no está en allowed_company_ids."""
        # Buscar quants en ubicaciones internas con allowed_company_ids definido
        quants_with_restriction = self.env['stock.quant'].sudo().search([
            ('location_id.usage', '=', 'internal'),
            ('location_id.allowed_company_ids', '!=', False),
            ('quantity', '!=', 0),
        ])

        incompatible = quants_with_restriction.filtered(
            lambda q: (
                q.company_id
                and q.location_id.allowed_company_ids
                and q.company_id not in q.location_id.allowed_company_ids
            )
        )

        if not incompatible:
            return 0, _('(ningún quant en ubicaciones incompatibles)')

        lines = []
        for q in incompatible[:50]:
            lines.append(
                '  Producto: %s | Ub: %s | Empresa quant: %s | Permitidas: [%s] | Cant: %.2f'
                % (
                    q.product_id.display_name,
                    q.location_id.complete_name,
                    q.company_id.name,
                    ', '.join(q.location_id.allowed_company_ids.mapped('name')),
                    q.quantity,
                )
            )
        if len(incompatible) > 50:
            lines.append(_('  ... y %d quants más') % (len(incompatible) - 50))

        return len(incompatible), '\n'.join(lines)

    def _diag_pickings(self):
        """S5: transferencias abiertas con ubicaciones incompatibles."""
        open_pickings = self.env['stock.picking'].sudo().search([
            ('state', 'not in', ['done', 'cancel']),
        ])

        incompatible = open_pickings.filtered(
            lambda p: bool(p._check_location_compatibility_silent())
        )

        if not incompatible:
            return 0, _('(ninguna transferencia abierta con incompatibilidades)')

        lines = []
        for picking in incompatible[:50]:
            issues = picking._check_location_compatibility_silent()
            lines.append(
                '  [%s] %s (empresa: %s, estado: %s)\n      %s'
                % (
                    picking.id,
                    picking.name,
                    picking.company_id.name if picking.company_id else '—',
                    picking.state,
                    '\n      '.join(issues),
                )
            )
        if len(incompatible) > 50:
            lines.append(_('  ... y %d transferencias más') % (len(incompatible) - 50))

        return len(incompatible), '\n'.join(lines)
