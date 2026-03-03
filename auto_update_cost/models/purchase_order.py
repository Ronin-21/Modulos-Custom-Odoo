# -*- coding: utf-8 -*-

import logging
from odoo import fields, models
from odoo.tools.float_utils import float_compare, float_round

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def button_confirm(self):
        icp = self.env['ir.config_parameter'].sudo()
        enabled = icp.get_param('auto_update_cost.enabled', 'True') == 'True'
        moment = icp.get_param('auto_update_cost.moment', 'receive')
        if enabled and moment == 'confirm':
            self._auc_update_standard_from_po()
        return super().button_confirm()

    def _auc_target_companies(self, order_company):
        scope = self.env['ir.config_parameter'].sudo().get_param('auto_update_cost.scope', 'all')
        return self.env['res.company'].sudo().search([]) if scope == 'all' else order_company

    def _auc_recalc_bom_enabled(self):
        return self.env['ir.config_parameter'].sudo().get_param('auto_update_cost.recalc_bom', 'True') == 'True'

    def _auc_po_line_unit_cost(self, line):
        """Costo unitario CON IVA (price_total) / qty. Luego se convierte a moneda compañía y se redondea a 2 dec."""
        if line.display_type:
            return None
        product = line.product_id
        if not product or product.type not in ('product', 'consu'):
            return None
        qty = line.product_qty or 0.0
        if not qty:
            return None

        # ✅ CON IVA
        unit_cost = line.price_total / qty

        # UoM -> UoM del producto
        if line.product_uom and product.uom_id and line.product_uom != product.uom_id:
            unit_cost = line.product_uom._compute_price(unit_cost, product.uom_id)

        return unit_cost

    def _auc_update_standard_from_po(self):
        icp = self.env['ir.config_parameter'].sudo()
        strategy = icp.get_param('auto_update_cost.standard_strategy', 'last')
        recalc_bom = self._auc_recalc_bom_enabled()

        for order in self:
            target_companies = self._auc_target_companies(order.company_id)
            date = order.date_order or fields.Date.today()

            updated_templates = self.env['product.template']
            updated_products = []  # ✅ NUEVO

            for line in order.order_line:
                unit_cost_order_currency = self._auc_po_line_unit_cost(line)
                if unit_cost_order_currency is None:
                    continue

                tmpl = line.product_id.product_tmpl_id
                if tmpl.cost_method != 'standard':
                    continue

                product_updated = False  # ✅ NUEVO

                for company in target_companies:
                    tmpl_c = tmpl.with_company(company)

                    incoming_cost = order.currency_id._convert(
                        unit_cost_order_currency,
                        company.currency_id,
                        company,
                        date,
                    )
                    incoming_cost = float_round(incoming_cost, precision_digits=2)

                    if strategy == 'last':
                        new_cost = incoming_cost
                    else:
                        avg = tmpl_c.auc_avg_simple_cost or 0.0
                        cnt = tmpl_c.auc_avg_simple_count or 0
                        new_cnt = cnt + 1
                        new_avg = ((avg * cnt) + incoming_cost) / new_cnt if new_cnt else incoming_cost
                        new_avg = float_round(new_avg, precision_digits=2)
                        new_cost = new_avg

                        tmpl_c.with_context(disable_auto_svl=True, skip_bom_recalc=True).sudo().write({
                            'auc_avg_simple_cost': new_avg,
                            'auc_avg_simple_count': new_cnt,
                        })

                    if float_compare(tmpl_c.standard_price, new_cost, precision_digits=2) != 0:
                        old_cost = tmpl_c.standard_price  # ✅ NUEVO
                        tmpl_c.with_context(disable_auto_svl=True, skip_bom_recalc=True).sudo().write({
                            'standard_price': new_cost
                        })
                        updated_templates |= tmpl
                        product_updated = True  # ✅ NUEVO

                # ✅ NUEVO: Agregar al resumen solo si se actualizó
                if product_updated:
                    updated_products.append(f"{line.product_id.name}: ${new_cost:,.2f}")

            # ✅ NUEVO: Mensaje al chatter
            if updated_products:
                scope_label = "todas las compañías" if len(target_companies) > 1 else order.company_id.name
                message = "".join(updated_products)
                order.message_post(
                    body=f"✓ Costos actualizados ({scope_label}):{message}"
                )

            if recalc_bom and updated_templates:
                for tmpl in updated_templates:
                    try:
                        tmpl._recalculate_bom_costs()
                    except Exception as e:
                        _logger.exception("AUC BoM error: %s", e)

        return True
