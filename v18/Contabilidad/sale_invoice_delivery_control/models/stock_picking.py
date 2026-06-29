from odoo import _, models
from odoo.exceptions import UserError

PARAM_REQUIRE_INVOICE = 'sale_invoice_delivery_control.require_posted_invoice_before_delivery'


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sidc_is_control_enabled(self):
        """Devuelve True si el parámetro global de control está activo."""
        param = self.env['ir.config_parameter'].sudo().get_param(
            PARAM_REQUIRE_INVOICE, default='True'
        )
        return param == 'True'

    def _sidc_has_storable_moves(self):
        """
        Devuelve True si el picking tiene al menos un movimiento de stock
        de un producto almacenable (is_storable / type == 'product').

        Excluye servicios, consumibles sin tracking, y líneas canceladas.
        """
        for move in self.move_ids:
            if move.state == 'cancel':
                continue
            product = move.product_id
            # Odoo 18: product.type == 'product' == almacenable (storable)
            # Compatibilidad: is_storable puede existir en algunas builds
            if getattr(product, 'is_storable', None) is not None:
                if product.is_storable:
                    return True
            elif product.type == 'product':
                return True
        return False

    def _sidc_has_confirmed_invoice(self, sale_order):
        """
        Devuelve True si la orden de venta tiene al menos una factura de
        cliente confirmada (out_invoice + posted).

        Notas de crédito y facturas en borrador/canceladas NO cuentan.
        """
        return any(
            inv.move_type == 'out_invoice' and inv.state == 'posted'
            for inv in sale_order.invoice_ids
        )

    # ------------------------------------------------------------------
    # Override principal
    # ------------------------------------------------------------------

    def button_validate(self):
        """
        Sobrescribe button_validate para bloquear entregas de salida de
        productos almacenables cuando la venta relacionada no tiene factura
        confirmada, si el parámetro global está activo.

        El bloqueo se aplica ANTES de llamar al super(), garantizando que
        funcione desde cualquier origen: UI, backend, RPC, acción masiva.
        """
        # Iterar sobre todos los pickings que van a validarse (puede ser
        # un recordset con varios registros en validación masiva).
        for picking in self:
            # 1. Solo entregas de salida
            if picking.picking_type_code != 'outgoing':
                continue

            # 2. Solo si está vinculado a una orden de venta
            sale = picking.sale_id
            if not sale:
                continue

            # 3. Solo si el picking contiene productos almacenables
            if not picking._sidc_has_storable_moves():
                continue

            # 4. Verificar si el control global está habilitado
            if not picking._sidc_is_control_enabled():
                continue

            # 5. Verificar factura confirmada
            if not picking._sidc_has_confirmed_invoice(sale):
                raise UserError(_(
                    "No se puede validar esta entrega porque la orden de venta "
                    "%(order)s todavía no tiene una factura confirmada.\n\n"
                    "Debe confirmar (publicar) la factura antes de entregar mercadería.",
                    order=sale.name,
                ))

        return super().button_validate()
