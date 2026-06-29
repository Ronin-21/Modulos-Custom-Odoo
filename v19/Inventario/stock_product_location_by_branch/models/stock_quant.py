import logging
from odoo import models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    # ══════════════════════════════════════════════════════════════════════════════
    # Override del ajuste de inventario
    # ══════════════════════════════════════════════════════════════════════════════

    def _apply_inventory(self, date=None):
        """
        Extiende _apply_inventory para bloquear ajustes que incrementen stock
        en una ubicación distinta a la configurada en stock.product.branch.location.

        Las reducciones de stock en ubicaciones no configuradas se permiten
        deliberadamente: son el mecanismo para corregir stock mal ubicado.
        """
        self._splb_validate_inventory_locations()
        return super()._apply_inventory(date=date)

    # ══════════════════════════════════════════════════════════════════════════════
    # Validación de ubicaciones
    # ══════════════════════════════════════════════════════════════════════════════

    def _splb_validate_inventory_locations(self):
        """
        Para cada quant del ajuste donde el stock va a AUMENTAR, verifica que:
          1. El producto tenga ubicación configurada en stock.product.branch.location.
          2. La ubicación del ajuste coincida con la configurada.

        Ambas condiciones son obligatorias: se bloquea si falta la config o si
        la ubicación no coincide. Las reducciones se permiten en cualquier ubicación
        para poder corregir stock mal ubicado.
        """
        errors_no_config = []
        errors_wrong_loc = []

        for quant in self:
            if not quant.product_id or not quant.product_id.is_storable:
                continue

            # Calcular diferencia sin depender del campo computado (puede no
            # estar actualizado antes de que super() llame inventory_quantity_set=True)
            diff = quant.inventory_quantity - quant.quantity
            if quant.product_uom_id.compare(diff, 0) < 0:
                # Reducción estrictamente negativa: permitida en cualquier ubicación
                # para poder corregir stock que fue mal ubicado previamente.
                continue

            warehouse = self._splb_get_warehouse_from_location(quant.location_id)
            if not warehouse:
                # Ubicación virtual o sin almacén: fuera del scope del módulo
                continue

            config = self.env['stock.product.branch.location'].sudo().search([
                ('product_id', '=', quant.product_id.id),
                ('warehouse_id', '=', warehouse.id),
                ('company_id', '=', warehouse.company_id.id),
                ('active', '=', True),
            ], limit=1)

            if not config or not config.location_id:
                errors_no_config.append(
                    _('• %(product)s  (almacén: %(wh)s)',
                      product=quant.product_id.display_name,
                      wh=warehouse.name)
                )
                continue

            if config.location_id.id != quant.location_id.id:
                errors_wrong_loc.append(_(
                    '• %(product)s\n'
                    '  Ajuste en:    %(adj_loc)s\n'
                    '  Habitual:     %(cfg_loc)s\n'
                    '  Almacén:      %(wh)s',
                    product=quant.product_id.display_name,
                    adj_loc=quant.location_id.complete_name,
                    cfg_loc=config.location_id.complete_name,
                    wh=warehouse.name,
                ))

        parts = []
        if errors_no_config:
            parts.append(
                _('Los siguientes productos no tienen ubicación habitual configurada '
                  'para su almacén. Configure la ubicación antes de realizar el ajuste:\n\n')
                + '\n'.join(errors_no_config)
            )
        if errors_wrong_loc:
            parts.append(
                _('Los siguientes productos están siendo ubicados en una posición '
                  'diferente a la habitual configurada. Use la ubicación habitual '
                  'o actualice la configuración:\n\n')
                + '\n\n'.join(errors_wrong_loc)
            )

        if parts:
            raise UserError(
                _('No se puede aplicar el ajuste de inventario.\n\n')
                + '\n\n'.join(parts)
                + _('\n\nConfigurá las ubicaciones en:\n'
                    'Inventario → Configuración → Ubicaciones por Producto/Sucursal')
            )

    # ══════════════════════════════════════════════════════════════════════════════
    # Helper: detección de almacén por jerarquía de ubicaciones
    # ══════════════════════════════════════════════════════════════════════════════

    def _splb_get_warehouse_from_location(self, location):
        """
        Detecta qué almacén contiene la ubicación dada usando parent_path.
        Retorna el almacén más específico (más profundo en la jerarquía).

        Método equivalente al de stock.picking — duplicado intencionalmente
        para mantener independencia entre modelos.
        """
        if not location or not location.parent_path:
            return self.env['stock.warehouse']

        loc_path = location.parent_path
        warehouses = self.env['stock.warehouse'].sudo().search([])
        best = self.env['stock.warehouse']
        best_depth = -1

        for wh in warehouses:
            if not wh.view_location_id or not wh.view_location_id.parent_path:
                continue
            wh_path = wh.view_location_id.parent_path
            if loc_path.startswith(wh_path):
                depth = wh_path.count('/')
                if depth > best_depth:
                    best = wh
                    best_depth = depth

        return best
