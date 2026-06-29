# -*- coding: utf-8 -*-
"""
stock_location_empresa_wizard.py
================================
Wizard: Detalle de compatibilidad por empresa.
Equivale al script DETALLE_POR_EMPRESA_v2 pero desde la UI de Odoo.
"""
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class StockLocationEmpresaWizard(models.TransientModel):
    _name = 'stock.location.empresa.wizard'
    _description = 'Detalle de Compatibilidad por Empresa'

    company_id = fields.Many2one(
        'res.company', string='Empresa a analizar', required=True,
        default=lambda self: self.env.company,
    )

    # Resultados
    summary = fields.Text('Resumen', readonly=True)
    loc_accesibles_text = fields.Text('Ubicaciones accesibles', readonly=True)
    loc_bloqueadas_text = fields.Text('Ubicaciones bloqueadas', readonly=True)
    quants_bloqueados_text = fields.Text('Quants en ubicaciones bloqueadas', readonly=True)
    move_lines_text = fields.Text('Move lines pendientes afectadas', readonly=True)

    loc_accesibles_count = fields.Integer(readonly=True)
    loc_bloqueadas_count = fields.Integer(readonly=True)
    quants_bloqueados_count = fields.Integer(readonly=True)
    move_lines_count = fields.Integer(readonly=True)

    estado = fields.Selection([
        ('draft', 'Sin ejecutar'),
        ('done', 'Ejecutado'),
    ], default='draft', readonly=True)

    def action_run(self):
        self.ensure_one()
        cid = self.company_id.id

        # ---- 1. Ubicaciones compartidas con quants ----
        self.env.cr.execute("""
            SELECT
                sl.id, sl.complete_name, sl.usage,
                COUNT(DISTINCT lacr.company_id)     AS allowed_count,
                COALESCE(
                    STRING_AGG(DISTINCT ac.name, ' | ' ORDER BY ac.name)
                      FILTER (WHERE ac.id IS NOT NULL),
                    '(vacío — sin restricción)'
                )                                   AS allowed_companies,
                BOOL_OR(lacr.company_id = %s)       AS company_included,
                COUNT(DISTINCT sq.id)               AS quant_count,
                SUM(COALESCE(sq.quantity, 0))       AS total_qty,
                SUM(COALESCE(sq.reserved_quantity,0)) AS total_reserved
            FROM stock_location sl
            JOIN stock_quant sq ON sq.location_id = sl.id
            LEFT JOIN stock_location_allowed_company_rel lacr ON lacr.location_id = sl.id
            LEFT JOIN res_company ac ON ac.id = lacr.company_id
            WHERE sl.company_id IS NULL
              AND sl.usage IN ('transit', 'internal')
            GROUP BY sl.id, sl.complete_name, sl.usage
            ORDER BY sl.usage, sl.complete_name
        """, [cid])
        locs = self.env.cr.dictfetchall()

        ok = [r for r in locs if r['allowed_count'] == 0 or r['company_included']]
        blocked = [r for r in locs if r['allowed_count'] > 0 and not r['company_included']]

        # ---- 2. Quants en ubicaciones bloqueadas ----
        blocked_loc_ids = [r['id'] for r in blocked]
        quants = []
        if blocked_loc_ids:
            self.env.cr.execute("""
                SELECT
                    sq.id AS quant_id,
                    COALESCE(pt.name->>'es_AR', pt.name->>'en_US') AS product_name,
                    pp.default_code,
                    sq.quantity, sq.reserved_quantity,
                    sl.complete_name AS location,
                    STRING_AGG(DISTINCT ac.name, ' | ' ORDER BY ac.name)
                        FILTER (WHERE ac.id IS NOT NULL) AS loc_allowed
                FROM stock_quant sq
                JOIN stock_location sl   ON sl.id = sq.location_id
                JOIN product_product pp  ON pp.id = sq.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN stock_location_allowed_company_rel lacr ON lacr.location_id = sl.id
                LEFT JOIN res_company ac ON ac.id = lacr.company_id
                WHERE sq.location_id = ANY(%s)
                GROUP BY sq.id, pt.name, pp.default_code, sq.quantity,
                         sq.reserved_quantity, sl.complete_name
                ORDER BY sl.complete_name, product_name
            """, [blocked_loc_ids])
            quants = self.env.cr.dictfetchall()

        # ---- 3. Move lines pendientes en ubicaciones bloqueadas ----
        pending_lines = []
        if blocked_loc_ids:
            self.env.cr.execute("""
                SELECT sml.id, sml.quantity, sm.name AS move_name,
                       sm.state AS move_state, sp.name AS picking_name,
                       sp.state AS picking_state,
                       sl_src.complete_name AS loc_src,
                       sl_dst.complete_name AS loc_dst
                FROM stock_move_line sml
                JOIN stock_move sm    ON sm.id = sml.move_id
                LEFT JOIN stock_picking sp ON sp.id = sm.picking_id
                JOIN stock_location sl_src ON sl_src.id = sml.location_id
                JOIN stock_location sl_dst ON sl_dst.id = sml.location_dest_id
                WHERE sm.state NOT IN ('done', 'cancel')
                  AND (sml.location_id = ANY(%s) OR sml.location_dest_id = ANY(%s))
                ORDER BY sp.name, sm.name
            """, [blocked_loc_ids, blocked_loc_ids])
            pending_lines = self.env.cr.dictfetchall()

        # ---- Formatear resultados ----
        def fmt_locs(rows):
            lines = []
            for r in rows:
                flag = '⚠ ABIERTA' if r['allowed_count'] == 0 else '✓ PERMITIDA' if r['company_included'] else '✗ BLOQUEADA'
                lines.append(
                    '[%s] %s (%s)  [%s]\n'
                    '  Permitidas: %s\n'
                    '  Quants: %s | Qty: %.2f | Reservado: %.2f'
                    % (r['id'], r['complete_name'], r['usage'], flag,
                       r['allowed_companies'], r['quant_count'], r['total_qty'], r['total_reserved'])
                )
            return '\n\n'.join(lines) or '(ninguna)'

        quant_lines = []
        cur_loc = None
        for r in quants:
            if r['location'] != cur_loc:
                cur_loc = r['location']
                quant_lines.append('\nUbicación: %s\nPermitidas: %s' % (r['location'], r['loc_allowed'] or '—'))
            flag = '  ⚠ RESERVADO' if r['reserved_quantity'] > 0 else ''
            cod = '[%s] ' % r['default_code'] if r['default_code'] else ''
            quant_lines.append('  Quant [%s] %s%s | Qty: %.2f | Res: %.2f%s'
                % (r['quant_id'], cod, r['product_name'], r['quantity'], r['reserved_quantity'], flag))

        ml_lines = []
        for r in pending_lines:
            icon = '⚠' if r['move_state'] not in ('done', 'cancel') else '·'
            ml_lines.append('%s MvLine [%s] qty=%.2f | Move: %s (%s) | Picking: %s (%s)\n    %s → %s'
                % (icon, r['id'], r['quantity'], r['move_name'], r['move_state'],
                   r['picking_name'], r['picking_state'], r['loc_src'], r['loc_dst']))

        summary = (
            '=== DETALLE EMPRESA: %s ===\n\n'
            'Ubicaciones accesibles:          %d\n'
            'Ubicaciones bloqueadas:          %d\n'
            'Quants en ubs. bloqueadas:       %d\n'
            'Move lines pendientes afectadas: %d'
        ) % (self.company_id.name, len(ok), len(blocked), len(quants), len(pending_lines))

        self.write({
            'estado': 'done',
            'summary': summary,
            'loc_accesibles_count': len(ok),
            'loc_bloqueadas_count': len(blocked),
            'quants_bloqueados_count': len(quants),
            'move_lines_count': len(pending_lines),
            'loc_accesibles_text': fmt_locs(ok),
            'loc_bloqueadas_text': fmt_locs(blocked),
            'quants_bloqueados_text': '\n'.join(quant_lines) or '(ninguno)',
            'move_lines_text': '\n'.join(ml_lines) or '(ninguna)',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_cleanup(self):
        """Abrir wizard de limpieza pre-cargado con esta empresa."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Limpieza de Quants'),
            'res_model': 'stock.location.cleanup.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_company_id': self.company_id.id},
        }
