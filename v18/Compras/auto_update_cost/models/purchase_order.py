# -*- coding: utf-8 -*-

import logging
from odoo import fields, models
from odoo.tools.float_utils import float_compare, float_round

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # ──────────────────────────────────────────────────────────────────────────
    # Override principal
    # ──────────────────────────────────────────────────────────────────────────

    def button_confirm(self):
        # FIX: super() primero — si falla, los costos NO se tocan.
        res = super().button_confirm()

        cfg = self.mapped('company_id')[:1].sudo()._auc_config() if self else {}
        if cfg.get('enabled') and cfg.get('moment') == 'confirm':
            self._auc_update_standard_from_po()

        return res

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _auc_target_companies(self, order_company, cfg):
        if cfg.get('scope') == 'all':
            return self.env['res.company'].sudo().search([])
        return order_company

    def _auc_po_line_unit_cost(self, line):
        """Devuelve el costo unitario CON IVA en la moneda de la OC, o None si no aplica."""
        if line.display_type:
            return None
        product = line.product_id
        if not product or product.type not in ('product', 'consu'):
            return None
        qty = line.product_qty or 0.0
        if not qty:
            return None

        unit_cost = line.price_total / qty

        if line.product_uom and product.uom_id and line.product_uom != product.uom_id:
            unit_cost = line.product_uom._compute_price(unit_cost, product.uom_id)

        return unit_cost

    # ──────────────────────────────────────────────────────────────────────────
    # Motor de actualización
    # ──────────────────────────────────────────────────────────────────────────

    def _auc_update_standard_from_po(self):
        for order in self:
            # Leer config UNA vez por orden (FIX: performance + fuente unificada)
            cfg = order.company_id.sudo()._auc_config()
            strategy = cfg['strategy']
            recalc_bom = cfg['recalc_bom']

            target_companies = self._auc_target_companies(order.company_id, cfg)
            date = order.date_order or fields.Date.today()

            updated_templates = self.env['product.template']
            chatter_lines = []

            for line in order.order_line:
                unit_cost_oc = self._auc_po_line_unit_cost(line)
                if unit_cost_oc is None:
                    continue

                tmpl = line.product_id.product_tmpl_id
                if tmpl.cost_method != 'standard':
                    continue

                product_updated = False
                # FIX: rastrear el costo de la compañía propietaria de la OC para el chatter
                display_cost = 0.0

                for company in target_companies:
                    try:
                        tmpl_c = tmpl.with_company(company)

                        incoming_cost = order.currency_id._convert(
                            unit_cost_oc,
                            company.currency_id,
                            company,
                            date,
                        )
                        incoming_cost = float_round(incoming_cost, precision_digits=2)

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
                                disable_auto_svl=True,
                                skip_bom_recalc=True,
                            ).sudo().write({
                                'auc_avg_simple_cost': new_avg,
                                'auc_avg_simple_count': new_cnt,
                            })

                        if float_compare(tmpl_c.standard_price, new_cost, precision_digits=2) != 0:
                            tmpl_c.with_context(
                                disable_auto_svl=True,
                                skip_bom_recalc=True,
                            ).sudo().write({'standard_price': new_cost})
                            updated_templates |= tmpl
                            product_updated = True

                    except Exception:
                        _logger.exception(
                            "AUC PO: error actualizando costo de '%s' en compañía '%s'",
                            line.product_id.display_name, company.name,
                        )

                if product_updated:
                    chatter_lines.append(
                        f"{line.product_id.display_name}: ${display_cost:,.2f}"
                    )

            # Chatter en la OC
            if chatter_lines:
                scope_label = (
                    "todas las compañías" if len(target_companies) > 1
                    else order.company_id.name
                )
                order.message_post(body=(
                    f"✓ Costos actualizados ({scope_label}):"
                    + "".join(chatter_lines) + ""
                ))

            # Recalculo BoM (una sola pasada por template)
            if recalc_bom and updated_templates:
                for tmpl in updated_templates:
                    try:
                        tmpl._recalculate_bom_costs()
                    except Exception:
                        _logger.exception("AUC BoM error en '%s'", tmpl.display_name)

        return True
