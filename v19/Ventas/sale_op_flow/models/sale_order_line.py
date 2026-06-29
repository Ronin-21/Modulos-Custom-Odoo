# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def action_view_branch_stock(self):
        """Abre el visor de stock del producto de la línea en todas las sucursales."""
        self.ensure_one()
        if not self.product_id:
            raise UserError(_('La línea no tiene un producto seleccionado.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stock en sucursales — %s') % self.product_id.display_name,
            'res_model': 'sof.product.branch.stock.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_product_id': self.product_id.id},
        }

    def _get_effective_pricelist(self):
        """
        En el flujo operativo SOF la lista de precios por línea no aplica:
        el pedido siempre usa una única lista (la general de la orden).

        Esta función ignora line_pricelist_id en pedidos SOF aunque el campo
        tuviera un valor (p. ej. cargado por RPC, importación o duplicación),
        garantizando que el precio se calcule siempre con la lista de la orden.
        En la vista, además, la columna queda oculta para pedidos SOF.
        """
        self.ensure_one()
        if self.order_id.is_sof_order:
            return self.order_id.pricelist_id
        return super()._get_effective_pricelist()
