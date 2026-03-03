# -*- coding: utf-8 -*-

import logging
from odoo import fields, models
from odoo.tools.float_utils import float_compare, float_round

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):
        res = super()._action_done(cancel_backorder=cancel_backorder)

        icp = self.env['ir.config_parameter'].sudo()
        enabled = icp.get_param('auto_update_cost.enabled', 'True') == 'True'
        moment = icp.get_param('auto_update_cost.moment', 'receive')
        if not enabled or moment != 'receive':
            return res

        scope = icp.get_param('auto_update_cost.scope', 'all')
        strategy = icp.get_param('auto_update_cost.standard_strategy', 'last')
        avco_replicate = icp.get_param('auto_update_cost.avco_replicate', 'True') == 'True'
        recalc_bom = icp.get_param('auto_update_cost.recalc_bom', 'True') == 'True'

        target_companies = self.env['res.company'].sudo().search([]) if scope == 'all' else self.env.company

        updated_templates = self.env['product.template']
        updated_pickings = {}  # ✅ NUEVO: {picking: [productos]}

        moves = self.filtered(lambda m: m.purchase_line_id and m.purchase_line_id.order_id and m.state == 'done')
        for move in moves:
            product = move.product_id
            if not product or product.type not in ('product', 'consu'):
                continue

            purchase_line = move.purchase_line_id
            order = purchase_line.order_id
            tmpl = product.product_tmpl_id
            date = order.date_order or fields.Date.today()

            changed_any = False
            new_cost_display = 0.0  # ✅ NUEVO

            # AVCO
            if tmpl.cost_method == 'average':
                if not avco_replicate:
                    continue

                base_cost = tmpl.with_company(order.company_id).standard_price
                from_currency = order.company_id.currency_id
                new_cost_display = base_cost  # ✅ NUEVO

                for company in target_companies:
                    if company == order.company_id:
                        continue

                    new_cost = from_currency._convert(base_cost, company.currency_id, company, date)
                    new_cost = float_round(new_cost, precision_digits=2)

                    tmpl_c = tmpl.with_company(company)
                    if float_compare(tmpl_c.standard_price, new_cost, precision_digits=2) != 0:
                        tmpl_c.with_context(disable_auto_svl=True, skip_bom_recalc=True).sudo().write({
                            'standard_price': new_cost
                        })
                        changed_any = True

            # Standard
            elif tmpl.cost_method == 'standard':
                qty_line = purchase_line.product_qty or 0.0
                unit_cost_order_currency = (purchase_line.price_total / qty_line) if qty_line else purchase_line.price_unit

                if purchase_line.product_uom and product.uom_id and purchase_line.product_uom != product.uom_id:
                    unit_cost_order_currency = purchase_line.product_uom._compute_price(unit_cost_order_currency, product.uom_id)

                for company in target_companies:
                    tmpl_c = tmpl.with_company(company)

                    incoming_cost = order.currency_id._convert(
                        unit_cost_order_currency,
                        company.currency_id,
                        company,
                        date,
                    )
                    incoming_cost = float_round(incoming_cost, precision_digits=2)
                    new_cost_display = incoming_cost  # ✅ NUEVO

                    if strategy == 'last':
                        new_cost = incoming_cost
                    else:
                        avg = tmpl_c.auc_avg_simple_cost or 0.0
                        cnt = tmpl_c.auc_avg_simple_count or 0
                        new_cnt = cnt + 1
                        new_avg = ((avg * cnt) + incoming_cost) / new_cnt if new_cnt else incoming_cost
                        new_avg = float_round(new_avg, precision_digits=2)
                        new_cost = new_avg
                        new_cost_display = new_avg  # ✅ NUEVO

                        tmpl_c.with_context(disable_auto_svl=True, skip_bom_recalc=True).sudo().write({
                            'auc_avg_simple_cost': new_avg,
                            'auc_avg_simple_count': new_cnt,
                        })

                    if float_compare(tmpl_c.standard_price, new_cost, precision_digits=2) != 0:
                        tmpl_c.with_context(disable_auto_svl=True, skip_bom_recalc=True).sudo().write({
                            'standard_price': new_cost
                        })
                        changed_any = True

            if changed_any:
                updated_templates |= tmpl
                # ✅ NUEVO: Agrupar por picking
                picking = move.picking_id
                if picking not in updated_pickings:
                    updated_pickings[picking] = []
                updated_pickings[picking].append(f"{product.name}: ${new_cost_display:,.2f}")

        # ✅ NUEVO: Mensaje al chatter del picking
        scope_label = "todas las compañías" if scope == 'all' else "compañía actual"
        for picking, products in updated_pickings.items():
            message = "".join(products)
            picking.message_post(
                body=f"✓ Costos actualizados ({scope_label}):{message}"
            )

        if recalc_bom and updated_templates:
            for tmpl in updated_templates:
                try:
                    tmpl._recalculate_bom_costs()
                except Exception as e:
                    _logger.exception("AUC BoM error: %s", e)

        return res
