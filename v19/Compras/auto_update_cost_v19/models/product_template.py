# -*- coding: utf-8 -*-

import logging
from odoo import fields, models
from odoo.tools.float_utils import float_compare, float_round

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Campos por compañía para el promedio simple (solo Standard)
    auc_avg_simple_cost = fields.Float(
        string='AUC Avg Cost (simple)',
        company_dependent=True,
        help='Promedio simple (aritmético) de precios de compra registrados por el módulo (solo Standard).',
    )
    auc_avg_simple_count = fields.Integer(
        string='AUC Avg Count (simple)',
        company_dependent=True,
        default=0,
        help='Cantidad de eventos usados para el promedio simple (solo Standard).',
    )

    # ──────────────────────────────────────────────────────────────────────────
    # Override write — propagación manual entre compañías
    # ──────────────────────────────────────────────────────────────────────────

    def write(self, vals):
        if self.env.context.get('skip_bom_recalc'):
            return super().write(vals)

        if 'standard_price' not in vals:
            return super().write(vals)

        old_prices = {p.id: p.standard_price for p in self}
        res = super().write(vals)

        cfg = self.env.company.sudo()._auc_config()
        propagate = cfg['propagate_manual']
        allow_avco_manual = cfg['propagate_avco']
        recalc_bom = cfg['recalc_bom']

        # ── Propagación a otras compañías ─────────────────────────────────────
        if propagate and not self.env.context.get('auc_skip_manual_cost_sync'):
            target_companies = self.env.user.company_ids
            current_company = self.env.company

            if len(target_companies) > 1:
                for product in self:
                    cost_method = product.cost_method
                    if cost_method != 'standard' and not (
                        allow_avco_manual and cost_method == 'average'
                    ):
                        continue

                    old_price = old_prices.get(product.id, 0.0)
                    if float_compare(product.standard_price, old_price, precision_digits=6) == 0:
                        continue

                    new_cost = product.with_company(current_company).standard_price

                    for company in target_companies:
                        if company == current_company:
                            continue
                        try:
                            p_company = product.with_company(company)
                            if float_compare(
                                p_company.standard_price, new_cost, precision_digits=6
                            ) != 0:
                                p_company.with_context(
                                    disable_auto_revaluation=True,
                                    skip_bom_recalc=True,
                                    auc_skip_manual_cost_sync=True,
                                ).sudo().write({'standard_price': new_cost})
                        except Exception:
                            _logger.exception(
                                "AUC propagación manual: error en '%s' compañía '%s'",
                                product.display_name, company.name,
                            )

        # ── Recalculo BoM ─────────────────────────────────────────────────────
        if not recalc_bom:
            return res

        for product in self:
            old_price = old_prices.get(product.id, 0.0)
            if float_compare(product.standard_price, old_price, precision_digits=6) != 0:
                try:
                    product._recalculate_bom_costs()
                except Exception:
                    _logger.exception("AUC BoM error en '%s'", product.display_name)

        return res

    # ──────────────────────────────────────────────────────────────────────────
    # Recalculo de BoM
    # ──────────────────────────────────────────────────────────────────────────

    def _recalculate_bom_costs(self):
        """
        Recalcula el standard_price del producto final cuya BoM contenga este
        componente. Solo opera sobre productos con costeo Standard.
        """
        self.ensure_one()

        if 'mrp.bom.line' not in self.env:
            return

        cfg = self.env.company.sudo()._auc_config()
        scope = cfg['scope']

        bom_lines = self.env['mrp.bom.line'].sudo().search([
            ('product_id.product_tmpl_id', '=', self.id)
        ])
        if not bom_lines:
            return

        boms = bom_lines.mapped('bom_id')
        target_companies = (
            self.env['res.company'].sudo().search([])
            if scope == 'all'
            else self.env.company
        )

        # Acumular para evitar escrituras duplicadas si múltiples componentes del mismo BoM se actualizan juntos.
        final_updates = {}  # {(tmpl_id, company_id): (final_tmpl, company, old_cost, new_cost)}

        for bom in boms:
            final_tmpl = bom.product_tmpl_id or (
                bom.product_id and bom.product_id.product_tmpl_id
            )
            if not final_tmpl or final_tmpl.cost_method != 'standard':
                continue

            for company in target_companies:
                try:
                    final_c = final_tmpl.with_company(company)
                    old_cost = final_c.standard_price
                    new_cost = float_round(
                        self._calculate_bom_cost(bom, company),
                        precision_digits=2,
                    )
                    if float_compare(old_cost, new_cost, precision_digits=2) != 0:
                        key = (final_tmpl.id, company.id)
                        final_updates[key] = (final_tmpl, final_c, company, old_cost, new_cost)
                except Exception:
                    _logger.exception(
                        "AUC BoM: error calculando costo de '%s' en compañía '%s'",
                        final_tmpl.display_name, company.name,
                    )

        for (final_tmpl, final_c, company, old_cost, new_cost) in final_updates.values():
            try:
                final_c.with_context(
                    disable_auto_revaluation=True,
                    skip_bom_recalc=True,
                ).sudo().write({'standard_price': new_cost})

                final_tmpl.with_company(company).message_post(
                    body=(
                        f"✓ BoM recalculado: "
                        f"${old_cost:,.2f} → ${new_cost:,.2f}"
                    )
                )
            except Exception:
                _logger.exception(
                    "AUC BoM write: error en '%s' compañía '%s'",
                    final_tmpl.display_name, company.name,
                )

    def _calculate_bom_cost(self, bom, company):
        """
        Calcula el costo de un producto final sumando sus componentes.
        Aplica product_efficiency de la BoM para reflejar merma/scrap.
        """
        total_cost = 0.0
        for line in bom.bom_line_ids:
            component = line.product_id
            if not component:
                continue

            component_cost = component.with_company(company).standard_price
            qty = line.product_qty

            if (line.product_uom_id and component.uom_id
                    and line.product_uom_id != component.uom_id):
                qty = line.product_uom_id._compute_quantity(qty, component.uom_id)

            total_cost += component_cost * qty

        if bom.product_qty and bom.product_qty > 0:
            total_cost = total_cost / bom.product_qty

        efficiency = getattr(bom, 'product_efficiency', 1.0) or 1.0
        if efficiency > 0:
            total_cost = total_cost / efficiency

        return total_cost
