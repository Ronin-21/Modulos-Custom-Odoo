# -*- coding: utf-8 -*-
import logging

from odoo import api, models
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = "stock.quant"

    @api.model
    def _mcc_safe_eval_domain(self, domain_value):
        if not domain_value:
            return []
        if isinstance(domain_value, (list, tuple)):
            return list(domain_value)
        try:
            value = safe_eval(domain_value)
            return value if isinstance(value, list) else []
        except Exception:
            _logger.warning("mcc: no se pudo evaluar dominio de acción stock.quant: %s", domain_value)
            return []

    @api.model
    def _mcc_safe_eval_context(self, context_value):
        if not context_value:
            return {}
        if isinstance(context_value, dict):
            return dict(context_value)
        try:
            value = safe_eval(context_value)
            return value if isinstance(value, dict) else {}
        except Exception:
            _logger.warning("mcc: no se pudo evaluar contexto de acción stock.quant: %s", context_value)
            return {}

    @api.model
    def _mcc_internal_locations_domain(self):
        return [("location_id.usage", "=", "internal")]

    @api.model
    def _mcc_apply_internal_only_to_action_dict(self, action):
        """Limita la acción visible de Ajustes de Inventario a ubicaciones internas.

        Importante: no se sobreescribe stock.quant._search ni read_group. El filtro
        se aplica solo al action dict que abre la pantalla. De esa forma no se
        rompen procesos técnicos de stock.quant como _quant_tasks() o
        _clean_reservations(), que Odoo ejecuta antes de abrir la vista.
        """
        if not isinstance(action, dict):
            return action

        current_domain = self._mcc_safe_eval_domain(action.get("domain"))
        internal_domain = self._mcc_internal_locations_domain()
        action["domain"] = expression.AND([current_domain, internal_domain])

        ctx = self._mcc_safe_eval_context(action.get("context"))
        ctx["inventory_mode"] = True
        ctx["mcc_inventory_internal_only"] = True
        action["context"] = ctx
        return action

    @api.model
    def action_view_inventory(self):
        """Acción estándar de Inventario físico/Ajustes de Inventario.

        La pantalla debe mostrar únicamente ubicaciones internas. Las ubicaciones
        de tránsito compartidas (ENVIO/*, DECOMISO/*, Inter-company transit, etc.)
        siguen existiendo y se siguen usando en los traslados, pero no forman
        parte del ajuste físico manual.
        """
        action = super().action_view_inventory()
        return self._mcc_apply_internal_only_to_action_dict(action)

    @api.model
    def _mcc_is_inventory_action_candidate(self, action):
        if action.res_model != "stock.quant":
            return False

        ctx = self._mcc_safe_eval_context(action.context)
        if ctx.get("inventory_mode") or ctx.get("mcc_inventory_internal_only"):
            return True

        name_value = action.name or ""
        if isinstance(name_value, dict):
            name = " ".join(str(v) for v in name_value.values()).lower()
        else:
            name = str(name_value).lower()
        keywords = [
            "inventory adjustment",
            "inventory adjustments",
            "ajuste de inventario",
            "ajustes de inventario",
            "inventario físico",
            "inventario fisico",
            "physical inventory",
        ]
        return any(k in name for k in keywords)

    @api.model
    def _mcc_configure_inventory_adjustment_actions(self):
        """Configura acciones de Ajustes de Inventario solo con ubicaciones internas.

        Esta función no toca contactos ni empresas permitidas de contactos.
        Solo actualiza acciones de stock.quant candidatas a Inventario físico.
        """
        Action = self.env["ir.actions.act_window"].sudo()
        actions = Action.search([("res_model", "=", "stock.quant")])
        internal_domain = self._mcc_internal_locations_domain()
        updated = 0

        for action in actions:
            if not self._mcc_is_inventory_action_candidate(action):
                continue

            ctx = self._mcc_safe_eval_context(action.context)
            original_key = "mcc_original_inventory_action_domain"

            if original_key in ctx:
                original_domain = self._mcc_safe_eval_domain(ctx.get(original_key))
            else:
                original_domain = self._mcc_safe_eval_domain(action.domain)
                ctx[original_key] = repr(original_domain)

            ctx["inventory_mode"] = True
            ctx["mcc_inventory_internal_only"] = True

            new_domain = expression.AND([original_domain, internal_domain])
            action.write({
                "domain": repr(new_domain),
                "context": repr(ctx),
            })
            updated += 1

        _logger.info("mcc: acciones de Ajustes de Inventario configuradas solo con ubicaciones internas: %s", updated)
        return True
