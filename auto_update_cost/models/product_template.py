# -*- coding: utf-8 -*-

import logging
from odoo import fields, models
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # ✅ Promedio simple de compras (solo Standard). Company-dependent para multi-empresa.
    auc_avg_simple_cost = fields.Float(
        string='AUC Avg Cost (simple)',
        company_dependent=True,
        help='Promedio simple (aritmético) de precios de compra registrados por el módulo (solo Standard).'
    )
    auc_avg_simple_count = fields.Integer(
        string='AUC Avg Count (simple)',
        company_dependent=True,
        default=0,
        help='Cantidad de eventos usados para el promedio simple (solo Standard).'
    )

    def write(self, vals):
        if self.env.context.get('skip_bom_recalc'):
            return super().write(vals)

        if 'standard_price' not in vals:
            return super().write(vals)

        old_prices = {p.id: p.standard_price for p in self}
        res = super().write(vals)

        icp = self.env['ir.config_parameter'].sudo()
        propagate = icp.get_param('auto_update_cost.propagate_manual_cost', 'False') == 'True'
        allow_avco_manual = icp.get_param('auto_update_cost.propagate_manual_cost_include_avco', 'False') == 'True'
        recalc_bom = icp.get_param('auto_update_cost.recalc_bom', 'True') == 'True'

        # Propagación manual: por defecto Standard; AVCO solo si el usuario habilita explícitamente.
        if propagate and not self.env.context.get('auc_skip_manual_cost_sync'):
            target_companies = self.env.user.company_ids
            current_company = self.env.company

            if len(target_companies) > 1:
                for product in self:
                    if product.cost_method != 'standard' and not (allow_avco_manual and product.cost_method == 'average'):
                        continue

                    old_price = old_prices.get(product.id, 0.0)
                    if float_compare(product.standard_price, old_price, precision_digits=6) == 0:
                        continue

                    new_cost = product.with_company(current_company).standard_price

                    for company in target_companies:
                        if company == current_company:
                            continue
                        p_company = product.with_company(company)
                        if float_compare(p_company.standard_price, new_cost, precision_digits=6) != 0:
                            p_company.with_context(
                                disable_auto_svl=True,
                                skip_bom_recalc=True,
                                auc_skip_manual_cost_sync=True,
                            ).sudo().write({'standard_price': new_cost})

        if not recalc_bom:
            return res

        for product in self:
            old_price = old_prices.get(product.id, 0.0)
            if float_compare(product.standard_price, old_price, precision_digits=6) != 0:
                try:
                    product._recalculate_bom_costs()
                except Exception as e:
                    _logger.exception("AUC BoM error: %s", e)

        return res

    def _recalculate_bom_costs(self):
        """Recalcula costos por BoM SOLO para productos Standard (seguro)."""
        self.ensure_one()

        if 'mrp.bom.line' not in self.env:
            return

        scope = self.env['ir.config_parameter'].sudo().get_param('auto_update_cost.scope', 'all')

        bom_lines = self.env['mrp.bom.line'].sudo().search([
            ('product_id.product_tmpl_id', '=', self.id)
        ])
        if not bom_lines:
            return

        boms = bom_lines.mapped('bom_id')
        target_companies = self.env['res.company'].sudo().search([]) if scope == 'all' else self.env.company

        for bom in boms:
            final_tmpl = bom.product_tmpl_id or (bom.product_id and bom.product_id.product_tmpl_id)
            if not final_tmpl or final_tmpl.cost_method != 'standard':
                continue

            for company in target_companies:
                final_c = final_tmpl.with_company(company)
                old_cost = final_c.standard_price
                new_cost = self._calculate_bom_cost(bom, company)
                if float_compare(old_cost, new_cost, precision_digits=6) != 0:
                    final_c.with_context(disable_auto_svl=True, skip_bom_recalc=True).sudo().write({'standard_price': new_cost})
                    
                    # ✅ NUEVO: Mensaje simple al chatter
                    final_tmpl.message_post(
                        body=f"✓ BoM recalculado: ${old_cost:,.2f} → ${new_cost:,.2f}"
                    )

    def _calculate_bom_cost(self, bom, company):
        total_cost = 0.0
        for line in bom.bom_line_ids:
            component = line.product_id
            if not component:
                continue
            component_cost = component.with_company(company).standard_price
            qty = line.product_qty
            if line.product_uom_id and component.uom_id and line.product_uom_id != component.uom_id:
                qty = line.product_uom_id._compute_quantity(qty, component.uom_id)
            total_cost += component_cost * qty

        if bom.product_qty and bom.product_qty > 0:
            total_cost = total_cost / bom.product_qty
        return total_cost
