# -*- coding: utf-8 -*-

import logging
from odoo import fields, models
from odoo.tools.float_utils import float_compare, float_round

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):
        res = super()._action_done(cancel_backorder=cancel_backorder)

        cfg = self.env.company.sudo()._auc_config()
        if not cfg['enabled'] or cfg['moment'] != 'receive':
            return res

        scope = cfg['scope']
        strategy = cfg['strategy']
        avco_replicate = cfg['avco_replicate']
        recalc_bom = cfg['recalc_bom']

        target_companies = (
            self.env['res.company'].sudo().search([])
            if scope == 'all'
            else self.env.company
        )

        updated_templates = self.env['product.template']
        updated_pickings = {}   # {picking: [líneas HTML]}

        moves = self.filtered(
            lambda m: m.purchase_line_id
            and m.purchase_line_id.order_id
            and m.state == 'done'
        )

        for move in moves:
            product = move.product_id
            # Odoo 19: product.type solo tiene 'consu' y 'service'
            if not product or product.type == 'service':
                continue

            purchase_line = move.purchase_line_id
            order = purchase_line.order_id
            tmpl = product.product_tmpl_id
            date = order.date_order or fields.Date.today()

            changed_any = False
            display_cost = 0.0

            # ── AVCO ──────────────────────────────────────────────────────────
            if tmpl.cost_method == 'average':
                if not avco_replicate:
                    continue

                base_cost = tmpl.with_company(order.company_id).standard_price
                from_currency = order.company_id.currency_id
                display_cost = base_cost

                for company in target_companies:
                    if company == order.company_id:
                        continue
                    try:
                        new_cost = float_round(
                            from_currency._convert(base_cost, company.currency_id, company, date),
                            precision_digits=2,
                        )
                        tmpl_c = tmpl.with_company(company)
                        if float_compare(tmpl_c.standard_price, new_cost, precision_digits=2) != 0:
                            tmpl_c.with_context(
                                disable_auto_revaluation=True,
                                skip_bom_recalc=True,
                            ).sudo().write({'standard_price': new_cost})
                            changed_any = True
                    except Exception:
                        _logger.exception(
                            "AUC AVCO receive: error en '%s' compañía '%s'",
                            product.display_name, company.name,
                        )

            # ── Standard ──────────────────────────────────────────────────────
            elif tmpl.cost_method == 'standard':
                qty_line = purchase_line.product_qty or 0.0
                unit_cost_oc = (
                    (purchase_line.price_total / qty_line)
                    if qty_line
                    else purchase_line.price_unit
                )

                if (purchase_line.product_uom_id and product.uom_id
                        and purchase_line.product_uom_id != product.uom_id):
                    unit_cost_oc = purchase_line.product_uom_id._compute_price(
                        unit_cost_oc, product.uom_id
                    )

                for company in target_companies:
                    try:
                        tmpl_c = tmpl.with_company(company)
                        incoming_cost = float_round(
                            order.currency_id._convert(
                                unit_cost_oc, company.currency_id, company, date
                            ),
                            precision_digits=2,
                        )

                        if company == order.company_id:
                            display_cost = incoming_cost

                        if strategy == 'last':
                            new_cost = incoming_cost
                        else:  # avg_simple
                            avg = tmpl_c.auc_avg_simple_cost or 0.0
                            cnt = tmpl_c.auc_avg_simple_count or 0
                            new_cnt = cnt + 1
                            new_avg = float_round(
                                ((avg * cnt) + incoming_cost) / new_cnt,
                                precision_digits=2,
                            )
                            new_cost = new_avg
                            if company == order.company_id:
                                display_cost = new_avg

                            tmpl_c.with_context(
                                disable_auto_revaluation=True,
                                skip_bom_recalc=True,
                            ).write({
                                'auc_avg_simple_cost': new_avg,
                                'auc_avg_simple_count': new_cnt,
                            })

                        if float_compare(tmpl_c.standard_price, new_cost, precision_digits=2) != 0:
                            tmpl_c.with_context(
                                disable_auto_revaluation=True,
                                skip_bom_recalc=True,
                            ).sudo().write({'standard_price': new_cost})
                            changed_any = True

                    except Exception:
                        _logger.exception(
                            "AUC Standard receive: error en '%s' compañía '%s'",
                            product.display_name, company.name,
                        )

            if changed_any:
                updated_templates |= tmpl
                picking = move.picking_id
                if picking not in updated_pickings:
                    updated_pickings[picking] = []
                updated_pickings[picking].append(
                    f"{product.display_name}: ${display_cost:,.2f}"
                )

        scope_label = "todas las compañías" if scope == 'all' else "compañía actual"
        for picking, lines in updated_pickings.items():
            picking.message_post(body=(
                f"✓ Costos actualizados ({scope_label}):"
                + "".join(lines) + ""
            ))

        if recalc_bom and updated_templates:
            for tmpl in updated_templates:
                try:
                    tmpl._recalculate_bom_costs()
                except Exception:
                    _logger.exception("AUC BoM error en '%s'", tmpl.display_name)

        return res
