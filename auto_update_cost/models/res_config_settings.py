# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    auto_update_cost_enabled = fields.Boolean(related='company_id.auc_enabled', readonly=False)

    auto_update_cost_moment = fields.Selection(related='company_id.auc_moment', readonly=False)

    auto_update_cost_scope = fields.Selection(related='company_id.auc_scope', readonly=False)

    auto_update_cost_standard_strategy = fields.Selection(related='company_id.auc_standard_strategy', readonly=False)

    auto_update_cost_avco_replicate = fields.Boolean(related='company_id.auc_avco_replicate', readonly=False)

    auto_update_cost_propagate_manual_cost = fields.Boolean(related='company_id.auc_propagate_manual_cost', readonly=False)

    auto_update_cost_propagate_manual_cost_include_avco = fields.Boolean(
        related='company_id.auc_propagate_manual_cost_include_avco',
        readonly=False
    )

    auto_update_cost_recalc_bom = fields.Boolean(related='company_id.auc_recalc_bom', readonly=False)
