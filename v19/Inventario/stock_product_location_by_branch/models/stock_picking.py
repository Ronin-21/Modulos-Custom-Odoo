import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_MODULE = 'stock_product_location_by_branch'


class StockPicking(models.Model):
    """
    Extiende stock.picking para:
    - Aplicar ubicaciones automáticas en recepciones y transferencias.
    - Proveer métodos auxiliares de búsqueda de configuración.
    - Ofrecer un botón manual de re-aplicación.
    """
    _inherit = 'stock.picking'

    splb_disable_auto = fields.Boolean(
        string='Desactivar ubicaciones automáticas',
        default=False,
        copy=False,
        help=(
            'Si está marcado, el módulo no modificará las ubicaciones de este '
            'albarán automáticamente. Útil para excepciones o correcciones manuales.'
        ),
    )

    # ══════════════════════════════════════════════════════════════════════════════
    # Helpers: lectura de parámetros de configuración
    # ══════════════════════════════════════════════════════════════════════════════

    def _splb_is_enabled(self, key, default=True):
        """
        Lee un parámetro booleano de ir.config_parameter.
        Retorna `default` si el parámetro no fue configurado aún.
        """
        val = self.env['ir.config_parameter'].sudo().get_param(
            '%s.%s' % (_MODULE, key)
        )
        if val is False or val == '':
            return default
        return val in ('True', '1', 'true')

    def _splb_get_str_param(self, key, default='warn'):
        """
        Lee un parámetro de texto de ir.config_parameter.
        """
        val = self.env['ir.config_parameter'].sudo().get_param(
            '%s.%s' % (_MODULE, key)
        )
        if val is False or val == '':
            return default
        return val

    # ══════════════════════════════════════════════════════════════════════════════
    # Helpers: búsqueda de configuración y warehouse
    # ══════════════════════════════════════════════════════════════════════════════

    def _splb_find_location(self, product, warehouse, company):
        """
        Busca la ubicación habitual configurada para product+warehouse+company.

        :param product: product.product record
        :param warehouse: stock.warehouse record
        :param company: res.company record
        :return: stock.location record o vacío
        """
        if not product or not warehouse or not company:
            return self.env['stock.location']

        config = self.env['stock.product.branch.location'].sudo().search([
            ('product_id', '=', product.id),
            ('warehouse_id', '=', warehouse.id),
            ('company_id', '=', company.id),
            ('active', '=', True),
        ], limit=1)

        if config and config.location_id and config.location_id.active:
            return config.location_id
        return self.env['stock.location']

    def _splb_get_warehouse_from_location(self, location):
        """
        Detecta qué almacén (stock.warehouse) contiene la ubicación dada,
        usando la jerarquía de parent_path.

        :param location: stock.location record
        :return: stock.warehouse record o vacío
        """
        if not location or not location.parent_path:
            return self.env['stock.warehouse']

        loc_path = location.parent_path

        # Buscar todos los almacenes; en multiempresa puede haber varios
        warehouses = self.env['stock.warehouse'].sudo().search([])
        best = self.env['stock.warehouse']
        best_depth = -1

        for wh in warehouses:
            if not wh.view_location_id or not wh.view_location_id.parent_path:
                continue
            wh_path = wh.view_location_id.parent_path
            if loc_path.startswith(wh_path):
                # Preferir el almacén cuya raíz esté más profunda (más específico)
                depth = wh_path.count('/')
                if depth > best_depth:
                    best = wh
                    best_depth = depth

        return best

    # ══════════════════════════════════════════════════════════════════════════════
    # Lógica de aplicación
    # ══════════════════════════════════════════════════════════════════════════════

    def _splb_apply_on_move(self, move):
        """
        Aplica las reglas de ubicación automática sobre un único stock.move.

        Modifica location_id y/o location_dest_id según el tipo de operación
        y la configuración del módulo.
        """
        if not move or move.state in ('done', 'cancel'):
            return

        picking = move.picking_id
        if not picking or picking.splb_disable_auto:
            return

        picking_code = picking.picking_type_code

        apply_receipts = self._splb_is_enabled('apply_on_receipts', True)
        apply_internals = self._splb_is_enabled('apply_on_internals', True)
        apply_lines = self._splb_is_enabled('apply_on_move_lines', True)
        missing_mode = self._splb_get_str_param('missing_config_mode', 'warn')

        if picking_code == 'incoming' and apply_receipts:
            self._splb_apply_incoming(move, apply_lines, missing_mode)

        elif picking_code == 'internal' and apply_internals:
            self._splb_apply_internal(move, apply_lines, missing_mode)

        # outgoing (sales) y otros tipos no se tocan

    def _splb_apply_incoming(self, move, apply_lines, missing_mode):
        """
        Recepción de compra: asigna location_dest_id habitual del producto
        en el almacén destino.
        """
        dest_wh = self._splb_get_warehouse_from_location(move.location_dest_id)

        if not dest_wh:
            _logger.debug(
                'SPLB [%s]: No se encontró almacén para la ubicación destino "%s".',
                move.picking_id.name, move.location_dest_id.display_name
            )
            return

        auto_loc = self._splb_find_location(
            move.product_id, dest_wh, dest_wh.company_id
        )

        if auto_loc:
            _logger.info(
                'SPLB [%s]: Asignando destino "%s" al producto "%s".',
                move.picking_id.name, auto_loc.complete_name, move.product_id.display_name
            )
            move.write({'location_dest_id': auto_loc.id})
            if apply_lines:
                undone_lines = move.move_line_ids.filtered(
                    lambda l: l.state not in ('done', 'cancel')
                )
                if undone_lines:
                    undone_lines.write({'location_dest_id': auto_loc.id})
        else:
            self._splb_handle_missing(
                move.picking_id,
                move.product_id,
                dest_wh,
                direction='destino',
                missing_mode=missing_mode,
            )

    def _splb_apply_internal(self, move, apply_lines, missing_mode):
        """
        Transferencia interna: asigna location_id (origen) y location_dest_id
        (destino) habituales del producto en los respectivos almacenes.
        """
        src_wh = self._splb_get_warehouse_from_location(move.location_id)
        dst_wh = self._splb_get_warehouse_from_location(move.location_dest_id)

        # ── Origen ──────────────────────────────────────────────────────────────
        if src_wh:
            auto_src = self._splb_find_location(
                move.product_id, src_wh, src_wh.company_id
            )
            if auto_src:
                _logger.info(
                    'SPLB [%s]: Asignando origen "%s" al producto "%s".',
                    move.picking_id.name, auto_src.complete_name, move.product_id.display_name
                )
                move.write({'location_id': auto_src.id})
                if apply_lines:
                    undone_lines = move.move_line_ids.filtered(
                        lambda l: l.state not in ('done', 'cancel')
                    )
                    if undone_lines:
                        undone_lines.write({'location_id': auto_src.id})
            else:
                self._splb_handle_missing(
                    move.picking_id,
                    move.product_id,
                    src_wh,
                    direction='origen',
                    missing_mode=missing_mode,
                )
        else:
            _logger.debug(
                'SPLB [%s]: No se encontró almacén para la ubicación origen "%s".',
                move.picking_id.name, move.location_id.display_name
            )

        # ── Destino ─────────────────────────────────────────────────────────────
        if dst_wh:
            auto_dst = self._splb_find_location(
                move.product_id, dst_wh, dst_wh.company_id
            )
            if auto_dst:
                _logger.info(
                    'SPLB [%s]: Asignando destino "%s" al producto "%s".',
                    move.picking_id.name, auto_dst.complete_name, move.product_id.display_name
                )
                move.write({'location_dest_id': auto_dst.id})
                if apply_lines:
                    undone_lines = move.move_line_ids.filtered(
                        lambda l: l.state not in ('done', 'cancel')
                    )
                    if undone_lines:
                        undone_lines.write({'location_dest_id': auto_dst.id})
            else:
                self._splb_handle_missing(
                    move.picking_id,
                    move.product_id,
                    dst_wh,
                    direction='destino',
                    missing_mode=missing_mode,
                )
        else:
            _logger.debug(
                'SPLB [%s]: No se encontró almacén para la ubicación destino "%s".',
                move.picking_id.name, move.location_dest_id.display_name
            )

    def _splb_handle_missing(self, picking, product, warehouse, direction, missing_mode):
        """
        Gestiona el caso de configuración ausente según el modo configurado.

        :param direction: 'origen' o 'destino' (para el mensaje)
        :param missing_mode: 'warn' → advertencia en chatter | 'block' → UserError
        """
        msg = _(
            'El producto "%(product)s" no tiene ubicación habitual configurada '
            'para el almacén %(direction)s "%(warehouse)s". '
            'Se utilizará la ubicación estándar del albarán.',
            product=product.display_name,
            direction=direction,
            warehouse=warehouse.name,
        )
        if missing_mode == 'block':
            raise UserError(msg)

        _logger.warning('SPLB: %s', msg)
        # Registrar advertencia en el chatter del albarán
        try:
            picking.message_post(
                body='⚠️ ' + msg,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )
        except Exception:
            pass  # No fallar si el chatter no está disponible

    def _splb_apply_on_picking(self):
        """
        Punto de entrada principal.
        Recorre todos los movimientos no validados del albarán y aplica la lógica.
        """
        for picking in self:
            if picking.splb_disable_auto:
                _logger.debug('SPLB: Albarán %s con auto-ubicación desactivada.', picking.name)
                continue
            for move in picking.move_ids:
                if move.state not in ('done', 'cancel'):
                    try:
                        self._splb_apply_on_move(move)
                    except UserError:
                        raise
                    except Exception as exc:
                        _logger.error(
                            'SPLB: Error inesperado al aplicar ubicación en movimiento '
                            '%s del albarán %s: %s',
                            move.id, picking.name, exc,
                            exc_info=True,
                        )

    # ══════════════════════════════════════════════════════════════════════════════
    # Hooks en el flujo estándar
    # ══════════════════════════════════════════════════════════════════════════════

    def action_confirm(self):
        """
        Sobreescribe action_confirm para aplicar ubicaciones automáticas
        justo después de confirmar el albarán.

        Aplica a:
        - incoming (recepciones de compras)
        - internal (transferencias entre sucursales)
        """
        res = super().action_confirm()

        eligible = self.filtered(
            lambda p: (
                p.picking_type_code in ('incoming', 'internal')
                and p.state not in ('done', 'cancel')
                and not p.splb_disable_auto
            )
        )
        if eligible:
            eligible._splb_apply_on_picking()

        return res

    # ══════════════════════════════════════════════════════════════════════════════
    # Acción de botón manual
    # ══════════════════════════════════════════════════════════════════════════════

    def action_splb_apply_auto_locations(self):
        """
        Botón manual en el formulario de albarán.
        Re-aplica ubicaciones automáticas sobre movimientos no validados.
        Útil cuando se añaden líneas después de la confirmación o para correcciones.
        """
        self.ensure_one()
        if self.state == 'done':
            raise UserError(
                _('No se pueden modificar las ubicaciones de un albarán ya validado.')
            )
        self._splb_apply_on_picking()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Ubicaciones aplicadas'),
                'message': _(
                    'Las ubicaciones habituales fueron aplicadas correctamente '
                    'a los movimientos pendientes.'
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
