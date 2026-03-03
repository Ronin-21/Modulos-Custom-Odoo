# -*- coding: utf-8 -*-

import logging
from odoo import fields, models
from odoo.tools.float_utils import float_compare, float_round

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        res = super().action_post()

        icp = self.env['ir.config_parameter'].sudo()
        enabled = icp.get_param('auto_update_cost.enabled', 'True') == 'True'
        moment = icp.get_param('auto_update_cost.moment', 'receive')
        if enabled and moment == 'invoice':
            bills = self.filtered(lambda m: m.move_type == 'in_invoice' and m.state == 'posted')
            if bills:
                bills._auc_update_standard_from_invoice()
        return res

    def _auc_update_standard_from_invoice(self):
        icp = self.env['ir.config_parameter'].sudo()
        scope = icp.get_param('auto_update_cost.scope', 'all')
        strategy = icp.get_param('auto_update_cost.standard_strategy', 'last')
        recalc_bom = icp.get_param('auto_update_cost.recalc_bom', 'True') == 'True'

        target_companies = self.env['res.company'].sudo().search([]) if scope == 'all' else self.env.company
        updated_templates = self.env['product.template']

        for move in self:
            date = move.invoice_date or fields.Date.today()
            updated_products = []  # ✅ NUEVO

            for line in move.invoice_line_ids:
                if line.display_type or not line.product_id or line.product_id.type not in ('product', 'consu'):
                    continue
                if not line.quantity:
                    continue

                tmpl = line.product_id.product_tmpl_id
                if tmpl.cost_method != 'standard':
                    continue

                unit_cost_inv_currency = line.price_total / line.quantity

                line_uom = getattr(line, 'product_uom_id', False)
                if line_uom and line.product_id.uom_id and line_uom != line.product_id.uom_id:
                    unit_cost_inv_currency = line_uom._compute_price(unit_cost_inv_currency, line.product_id.uom_id)

                product_updated = False  # ✅ NUEVO

                for company in target_companies:
                    tmpl_c = tmpl.with_company(company)

                    incoming_cost = move.currency_id._convert(
                        unit_cost_inv_currency,
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
                scope_label = "todas las compañías" if len(target_companies) > 1 else move.company_id.name
                message = "".join(updated_products)
                move.message_post(
                    body=f"✓ Costos actualizados ({scope_label}):{message}"
                )

        if recalc_bom and updated_templates:
            for tmpl in updated_templates:
                try:
                    tmpl._recalculate_bom_costs()
                except Exception as e:
                    _logger.exception("AUC BoM error: %s", e)

        return True
