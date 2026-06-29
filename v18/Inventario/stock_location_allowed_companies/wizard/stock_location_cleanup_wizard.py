# -*- coding: utf-8 -*-
"""
stock_location_cleanup_wizard.py
================================
Wizard: Limpieza de quants en ubicaciones bloqueadas.
Equivale al script LIMPIEZA_v2 pero desde la UI de Odoo.

Flujo:
  1. Elegir empresa (y opcionalmente ubicaciones)
  2. Clic "Vista previa" → muestra qué se va a tocar
  3. Revisar el reporte
  4. Clic "Ejecutar limpieza" → aplica los cambios con backups
"""
import logging
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockLocationCleanupWizard(models.TransientModel):
    _name = 'stock.location.cleanup.wizard'
    _description = 'Limpieza de Quants en Ubicaciones Bloqueadas'

    # ---- Configuración ----
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company,
        help='Empresa para la que se limpiarán los quants en ubicaciones no permitidas.',
    )
    location_ids = fields.Many2many(
        'stock.location',
        string='Ubicaciones (opcional)',
        domain=[('usage', 'in', ['transit', 'internal']), ('company_id', '=', False)],
        help='Si se deja vacío, se auto-detectan todas las ubicaciones bloqueadas para la empresa.',
    )
    skip_reserved = fields.Boolean(
        string='Omitir quants reservados',
        default=True,
        help='Si está marcado, no se tocan quants con cantidad reservada > 0. Recomendado.',
    )

    # ---- Estado ----
    state = fields.Selection([
        ('draft', 'Configuración'),
        ('preview', 'Vista previa'),
        ('done', 'Ejecutado'),
    ], default='draft', readonly=True)

    # ---- Resultados de vista previa ----
    preview_summary = fields.Text('Resumen de impacto', readonly=True)
    preview_quants_text = fields.Text('Quants a eliminar', readonly=True)
    preview_orphans_text = fields.Text('Move lines que quedarán con quant_id=NULL', readonly=True)
    preview_moves_text = fields.Text('Movimientos a desreservar', readonly=True)
    preview_pickings_text = fields.Text('Transferencias afectadas', readonly=True)

    quants_count = fields.Integer('Quants a eliminar', readonly=True)
    orphans_count = fields.Integer('Move lines huérfanas', readonly=True)
    moves_count = fields.Integer('Movimientos a desreservar', readonly=True)
    pickings_count = fields.Integer('Transferencias afectadas', readonly=True)

    # ---- Resultado de ejecución ----
    execution_log = fields.Text('Log de ejecución', readonly=True)
    backup_tag = fields.Char('Tag de backup', readonly=True)

    # ---- Helpers internos ----

    def _get_target_location_ids(self):
        """Devuelve IDs de ubicaciones bloqueadas para la empresa."""
        if self.location_ids:
            return self.location_ids.ids

        self.env.cr.execute("""
            SELECT DISTINCT sl.id
            FROM stock_location sl
            JOIN stock_location_allowed_company_rel lacr ON lacr.location_id = sl.id
            WHERE sl.company_id IS NULL
              AND sl.usage IN ('transit', 'internal')
              AND NOT EXISTS (
                    SELECT 1 FROM stock_location_allowed_company_rel ok
                    WHERE ok.location_id = sl.id AND ok.company_id = %s
              )
        """, [self.company_id.id])
        return [r[0] for r in self.env.cr.fetchall()]

    def _get_target_quants(self, loc_ids):
        reserved_filter = "AND sq.reserved_quantity = 0" if self.skip_reserved else ""
        self.env.cr.execute(f"""
            SELECT sq.id AS quant_id, sq.product_id,
                   COALESCE(pt.name->>'es_AR', pt.name->>'en_US') AS product_name,
                   pp.default_code, sq.quantity, sq.reserved_quantity,
                   sl.complete_name AS location
            FROM stock_quant sq
            JOIN stock_location sl   ON sl.id = sq.location_id
            JOIN product_product pp  ON pp.id = sq.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE sq.location_id = ANY(%s)
              AND NOT EXISTS (
                    SELECT 1 FROM stock_location_allowed_company_rel lacr
                    WHERE lacr.location_id = sq.location_id
                      AND lacr.company_id = %s
              )
              {reserved_filter}
            ORDER BY sl.complete_name, product_name
        """, [loc_ids, self.company_id.id])
        return self.env.cr.dictfetchall()

    def _get_orphan_lines(self, quant_ids):
        if not quant_ids:
            return []
        self.env.cr.execute("""
            SELECT sml.id, sml.quantity, sml.quant_id,
                   sm.name AS move_name, sm.state AS move_state,
                   sp.name AS picking_name, sp.state AS picking_state,
                   sl_src.complete_name AS loc_src,
                   sl_dst.complete_name AS loc_dst
            FROM stock_move_line sml
            JOIN stock_move sm    ON sm.id = sml.move_id
            LEFT JOIN stock_picking sp ON sp.id = sm.picking_id
            JOIN stock_location sl_src ON sl_src.id = sml.location_id
            JOIN stock_location sl_dst ON sl_dst.id = sml.location_dest_id
            WHERE sml.quant_id = ANY(%s)
            ORDER BY sp.name, sm.name
        """, [quant_ids])
        return self.env.cr.dictfetchall()

    def _get_pending_moves(self, loc_ids):
        if not loc_ids:
            return []
        self.env.cr.execute("""
            SELECT DISTINCT sm.id, sm.name, sm.state,
                   sp.name AS picking_name, sp.state AS picking_state
            FROM stock_move sm
            JOIN stock_move_line sml ON sml.move_id = sm.id
            LEFT JOIN stock_picking sp ON sp.id = sm.picking_id
            WHERE sm.state NOT IN ('done', 'cancel')
              AND (sml.location_id = ANY(%s) OR sml.location_dest_id = ANY(%s))
            ORDER BY sm.state, sm.name
        """, [loc_ids, loc_ids])
        return self.env.cr.dictfetchall()

    def _get_pending_pickings(self, loc_ids):
        if not loc_ids:
            return []
        self.env.cr.execute("""
            SELECT DISTINCT sp.id, sp.name, sp.state
            FROM stock_picking sp
            JOIN stock_move sm ON sm.picking_id = sp.id
            JOIN stock_move_line sml ON sml.move_id = sm.id
            WHERE sp.state NOT IN ('done', 'cancel')
              AND (sml.location_id = ANY(%s) OR sml.location_dest_id = ANY(%s))
            ORDER BY sp.state, sp.name
        """, [loc_ids, loc_ids])
        return self.env.cr.dictfetchall()

    # ---- Acciones ----

    def action_preview(self):
        """Calcula el impacto sin modificar nada."""
        self.ensure_one()

        loc_ids = self._get_target_location_ids()
        if not loc_ids:
            raise UserError(_(
                'No se detectaron ubicaciones bloqueadas para la empresa "%s".\n'
                'Verifique que las ubicaciones tengan allowed_company_ids configurado '
                'y que esta empresa no esté incluida.'
            ) % self.company_id.name)

        quants = self._get_target_quants(loc_ids)
        quant_ids = [r['quant_id'] for r in quants]
        orphans = self._get_orphan_lines(quant_ids)
        moves = self._get_pending_moves(loc_ids)
        pickings = self._get_pending_pickings(loc_ids)

        # Formatear quants
        q_lines = []
        cur_loc = None
        for r in quants:
            if r['location'] != cur_loc:
                cur_loc = r['location']
                q_lines.append('\nUbicación: %s' % r['location'])
            flag = '  ⚠ RESERVADO' if r['reserved_quantity'] > 0 else ''
            cod = '[%s] ' % r['default_code'] if r['default_code'] else ''
            q_lines.append('  Quant [%s] %s%s | Qty: %.2f | Res: %.2f%s'
                % (r['quant_id'], cod, r['product_name'],
                   r['quantity'], r['reserved_quantity'], flag))

        # Formatear orphans
        o_lines = []
        for r in orphans:
            icon = '⚠' if r['move_state'] not in ('done', 'cancel') else '·'
            o_lines.append('%s MvLine [%s] qty=%.2f | Move: %s (%s) | Picking: %s (%s)\n    %s → %s'
                % (icon, r['id'], r['quantity'], r['move_name'], r['move_state'],
                   r['picking_name'] or '—', r['picking_state'] or '—',
                   r['loc_src'], r['loc_dst']))

        # Formatear moves
        m_lines = ['  Move [%s] %s (%s) | Picking: %s (%s)'
            % (r['id'], r['name'], r['state'], r['picking_name'] or '—', r['picking_state'] or '—')
            for r in moves]

        # Formatear pickings
        p_lines = ['  Picking [%s] %s (%s)' % (r['id'], r['name'], r['state'])
            for r in pickings]

        # Advertencias
        warnings = []
        open_orphans = [r for r in orphans if r['move_state'] not in ('done', 'cancel')]
        if open_orphans:
            warnings.append('⚠ ADVERTENCIA: %d move lines ABIERTAS quedarán con quant_id=NULL. '
                'Considere cerrar esas transferencias primero.' % len(open_orphans))
        if self.skip_reserved:
            warnings.append('SKIP_RESERVED=True: quants con reserva activa son omitidos.')

        summary_parts = [
            '=== VISTA PREVIA DE LIMPIEZA ===',
            'Empresa:                  %s' % self.company_id.name,
            'Ubicaciones bloqueadas:   %d' % len(loc_ids),
            'Quants a eliminar:        %d' % len(quants),
            'Qty total involucrada:    %.2f' % sum(r['quantity'] for r in quants),
            'Move lines → quant=NULL:  %d' % len(orphans),
            'Movimientos a desreservar:%d' % len(moves),
            'Transferencias afectadas: %d' % len(pickings),
        ]
        if warnings:
            summary_parts.append('')
            summary_parts.extend(warnings)

        self.write({
            'state': 'preview',
            'quants_count': len(quants),
            'orphans_count': len(orphans),
            'moves_count': len(moves),
            'pickings_count': len(pickings),
            'preview_summary': '\n'.join(summary_parts),
            'preview_quants_text': '\n'.join(q_lines) or '(ningún quant a eliminar)',
            'preview_orphans_text': '\n'.join(o_lines) or '(ninguna — seguro)',
            'preview_moves_text': '\n'.join(m_lines) or '(ninguno)',
            'preview_pickings_text': '\n'.join(p_lines) or '(ninguna)',
        })

        return {'type': 'ir.actions.act_window', 'res_model': self._name,
                'res_id': self.id, 'view_mode': 'form', 'target': 'new'}

    def action_execute(self):
        """Ejecuta la limpieza con backups completos."""
        self.ensure_one()
        if self.state != 'preview':
            raise UserError(_('Ejecute "Vista previa" antes de aplicar la limpieza.'))
        if self.quants_count == 0:
            raise UserError(_('No hay quants a eliminar. Nada que hacer.'))

        tag = datetime.now().strftime('%Y%m%d_%H%M%S')
        log = ['Inicio limpieza tag=%s  empresa=%s' % (tag, self.company_id.name)]

        loc_ids = self._get_target_location_ids()
        quants = self._get_target_quants(loc_ids)
        quant_ids = [r['quant_id'] for r in quants]
        orphans = self._get_orphan_lines(quant_ids)
        orphan_ids = [r['id'] for r in orphans]
        moves = self._get_pending_moves(loc_ids)
        move_ids = [r['id'] for r in moves]

        # Backup quants
        self.env.cr.execute(
            f"CREATE TABLE IF NOT EXISTS _backup_quants_{tag} AS "
            "SELECT sq.* FROM stock_quant sq WHERE sq.id = ANY(%s)",
            [quant_ids]
        )
        self.env.cr.commit()
        log.append('Backup quants: _backup_quants_%s (%d filas)' % (tag, len(quant_ids)))

        # Backup move lines
        if orphan_ids:
            self.env.cr.execute(
                f"CREATE TABLE IF NOT EXISTS _backup_move_lines_{tag} AS "
                "SELECT sml.* FROM stock_move_line sml WHERE sml.id = ANY(%s)",
                [orphan_ids]
            )
            self.env.cr.commit()
            log.append('Backup move lines: _backup_move_lines_%s (%d filas)' % (tag, len(orphan_ids)))

        # Backup movimientos
        if move_ids:
            self.env.cr.execute(
                f"CREATE TABLE IF NOT EXISTS _backup_moves_{tag} AS "
                "SELECT sm.* FROM stock_move sm WHERE sm.id = ANY(%s)",
                [move_ids]
            )
            self.env.cr.commit()
            log.append('Backup moves: _backup_moves_%s (%d filas)' % (tag, len(move_ids)))

        # Desreservar movimientos por ORM
        if move_ids:
            moves_obj = self.env['stock.move'].sudo().browse(move_ids)
            moves_obj._do_unreserve()
            self.env.cr.commit()
            log.append('Movimientos desreservados por ORM: %d' % len(move_ids))

        # Forzar reserved_quantity = 0 (safety net)
        self.env.cr.execute(
            "UPDATE stock_quant SET reserved_quantity = 0, write_date = NOW() WHERE id = ANY(%s)",
            [quant_ids]
        )
        self.env.cr.commit()
        log.append('reserved_quantity forzado a 0: %d quants' % self.env.cr.rowcount)

        # Limpiar quant_id en move lines huérfanas
        if orphan_ids:
            self.env.cr.execute(
                "UPDATE stock_move_line SET quant_id = NULL WHERE id = ANY(%s)",
                [orphan_ids]
            )
            self.env.cr.commit()
            log.append('quant_id → NULL en move lines: %d' % self.env.cr.rowcount)

        # Eliminar quants
        self.env.cr.execute("DELETE FROM stock_quant WHERE id = ANY(%s)", [quant_ids])
        deleted = self.env.cr.rowcount
        self.env.cr.commit()
        log.append('Quants eliminados: %d' % deleted)

        log.append('\n✓ Limpieza completada.')
        log.append('Para recuperar: SELECT * FROM _backup_quants_%s' % tag)
        _logger.info('StockLocationCleanupWizard: %s', '\n'.join(log))

        self.write({
            'state': 'done',
            'backup_tag': tag,
            'execution_log': '\n'.join(log),
        })

        return {'type': 'ir.actions.act_window', 'res_model': self._name,
                'res_id': self.id, 'view_mode': 'form', 'target': 'new'}
