# -*- coding: utf-8 -*-

import logging
from odoo import fields, models
from odoo.tools.float_utils import float_compare, float_round

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ──────────────────────────────────────────────────────────────────────────
    # Override principal
    # ──────────────────────────────────────────────────────────────────────────

    def action_post(self):
        res = super().action_post()

        # NO pre-filtramos por config aquí: la compañía del environment puede
        # diferir de move.company_id. El chequeo se hace por factura en el motor.
        bills = self.filtered(
            lambda m: m.move_type == 'in_invoice' and m.state == 'posted'
        )
        if bills:
            bills._auc_update_from_invoice()

        return res

    # ──────────────────────────────────────────────────────────────────────────
    # Motor de actualización — funciona con y sin Orden de Compra
    # ──────────────────────────────────────────────────────────────────────────

    def _auc_update_from_invoice(self):
        """
        Actualiza standard_price (Standard) y replica costo (AVCO) a partir de
        líneas de factura de proveedor.

        ✔ Funciona con facturas originadas desde una OC.
        ✔ Funciona con facturas directas sin OC.

        ODOO 18: las líneas de producto tienen display_type='product' (no False).
        El filtro correcto es display_type NOT IN ('line_section', 'line_note'),
        NO el antiguo `if line.display_type`.
        """
        for move in self:
            _logger.info(
                "AUC invoice: procesando '%s' (compañía: %s)",
                move.name, move.company_id.name,
            )

            try:
                cfg = move.company_id.sudo()._auc_config()
            except AttributeError:
                _logger.warning(
                    "AUC invoice: _auc_config() no disponible en res.company. "
                    "¿Módulo correctamente actualizado? Saltando '%s'.",
                    move.name,
                )
                continue

            _logger.info(
                "AUC invoice: cfg '%s' → enabled=%s, moment=%s, scope=%s, strategy=%s",
                move.name, cfg['enabled'], cfg['moment'], cfg['scope'], cfg['strategy'],
            )

            if not cfg['enabled']:
                _logger.info(
                    "AUC invoice: desactivado para '%s'. Activalo en Ajustes → "
                    "Precio de Costo Automático.", move.company_id.name,
                )
                continue

            if cfg['moment'] != 'invoice':
                _logger.info(
                    "AUC invoice: momento='%s' (necesita 'invoice'). "
                    "Cambialo en Ajustes → Precio de Costo Automático.",
                    cfg['moment'],
                )
                continue

            scope          = cfg['scope']
            strategy       = cfg['strategy']
            avco_replicate = cfg['avco_replicate']
            recalc_bom     = cfg['recalc_bom']

            target_companies = (
                self.env['res.company'].sudo().search([])
                if scope == 'all'
                else move.company_id
            )

            date = move.invoice_date or fields.Date.today()
            updated_templates = self.env['product.template']
            chatter_lines = []

            for line in move.invoice_line_ids:
                # FIX ODOO 18: en facturas, líneas de producto tienen
                # display_type='product'. El antiguo `if line.display_type`
                # era True para TODOS los tipos y saltaba todo.
                # Saltamos solo secciones y notas, procesamos 'product' y False.
                if line.display_type in ('line_section', 'line_note'):
                    continue

                product = line.product_id
                if not product or product.type not in ('product', 'consu'):
                    continue
                if not line.quantity:
                    continue

                tmpl = product.product_tmpl_id

                # ── AVCO ──────────────────────────────────────────────────────
                if tmpl.cost_method == 'average':
                    if not avco_replicate:
                        continue

                    base_cost = tmpl.with_company(move.company_id).standard_price
                    from_currency = move.company_id.currency_id
                    display_cost = base_cost
                    changed_any = False

                    for company in target_companies:
                        if company == move.company_id:
                            continue
                        try:
                            new_cost = float_round(
                                from_currency._convert(
                                    base_cost, company.currency_id, company, date
                                ),
                                precision_digits=2,
                            )
                            tmpl_c = tmpl.with_company(company)
                            if float_compare(tmpl_c.standard_price, new_cost, precision_digits=2) != 0:
                                tmpl_c.with_context(
                                    disable_auto_svl=True,
                                    skip_bom_recalc=True,
                                ).sudo().write({'standard_price': new_cost})
                                changed_any = True
                        except Exception:
                            _logger.exception(
                                "AUC AVCO invoice: error en '%s' compañía '%s'",
                                product.display_name, company.name,
                            )

                    if changed_any:
                        updated_templates |= tmpl
                        chatter_lines.append(
                            f"<li>{product.display_name} (AVCO replicado): "
                            f"<b>${display_cost:,.2f}</b></li>"
                        )

                # ── Standard ──────────────────────────────────────────────────
                elif tmpl.cost_method == 'standard':
                    # Costo unitario CON IVA — funciona con o sin OC vinculada
                    unit_cost_inv = line.price_total / line.quantity

                    # product_uom_id existe en Odoo 18 (verificado en fuente)
                    if line.product_uom_id and product.uom_id and line.product_uom_id != product.uom_id:
                        unit_cost_inv = line.product_uom_id._compute_price(unit_cost_inv, product.uom_id)

                    _logger.info(
                        "AUC invoice: '%s' cost_method=standard unit_cost=%.4f",
                        product.display_name, unit_cost_inv,
                    )

                    product_updated = False
                    display_cost = 0.0

                    for company in target_companies:
                        try:
                            tmpl_c = tmpl.with_company(company)
                            incoming_cost = float_round(
                                move.currency_id._convert(
                                    unit_cost_inv, company.currency_id, company, date
                                ),
                                precision_digits=2,
                            )

                            if company == move.company_id:
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
                                if company == move.company_id:
                                    display_cost = new_avg

                                tmpl_c.with_context(
                                    disable_auto_svl=True,
                                    skip_bom_recalc=True,
                                ).sudo().write({
                                    'auc_avg_simple_cost': new_avg,
                                    'auc_avg_simple_count': new_cnt,
                                })

                            _logger.info(
                                "AUC invoice: '%s' company='%s' current=%.2f → new=%.2f",
                                product.display_name, company.name,
                                tmpl_c.standard_price, new_cost,
                            )

                            if float_compare(tmpl_c.standard_price, new_cost, precision_digits=2) != 0:
                                tmpl_c.with_context(
                                    disable_auto_svl=True,
                                    skip_bom_recalc=True,
                                ).sudo().write({'standard_price': new_cost})
                                updated_templates |= tmpl
                                product_updated = True

                        except Exception:
                            _logger.exception(
                                "AUC Standard invoice: error en '%s' compañía '%s'",
                                product.display_name, company.name,
                            )

                    if product_updated:
                        chatter_lines.append(
                            f"{product.display_name}: ${display_cost:,.2f}"
                        )

            if chatter_lines:
                scope_label = (
                    "todas las compañías" if len(target_companies) > 1
                    else move.company_id.name
                )
                move.message_post(body=(
                    f"✓ Costos actualizados ({scope_label}):"
                    + "".join(chatter_lines) + ""
                ))

            if recalc_bom and updated_templates:
                for tmpl in updated_templates:
                    try:
                        tmpl._recalculate_bom_costs()
                    except Exception:
                        _logger.exception("AUC BoM error en '%s'", tmpl.display_name)

        return True
