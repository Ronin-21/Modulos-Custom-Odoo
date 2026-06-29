# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class PrsExpenseConcept(models.Model):
    _name = 'prs.expense.concept'
    _description = 'Conceptos de gastos'
    _parent_name = 'parent_id'
    _parent_store = True
    _order = 'complete_name'

    name = fields.Char(required=True, index=True)
    parent_id = fields.Many2one('prs.expense.concept', index=True, ondelete='restrict')
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('prs.expense.concept', 'parent_id', string="Subconceptos")
    complete_name = fields.Char(compute='_compute_complete_name', store=True, index=True, recursive=True)

    active = fields.Boolean(default=True)

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for rec in self:
            if rec.parent_id:
                rec.complete_name = f"{rec.parent_id.complete_name} / {rec.name}"
            else:
                rec.complete_name = rec.name
    def _register_hook(self):
        res = super()._register_hook()
        try:
            self._prs_reparent_expense_concept_menu()
        except Exception:
            _logger.exception("PRS: could not reparent expense concept menu")
        return res

    def _prs_reparent_expense_concept_menu(self):
        env = self.env

        menu = env.ref('payment_register_statement.menu_prs_expense_concept', raise_if_not_found=False)
        if not menu:
            return
        menu = menu.sudo()

        mgmt_menu = None
        for xmlid in (
            'account.menu_finance_configuration_management',
            'account_accountant.menu_finance_configuration_management',
            'account.menu_finance_configuration_management_accounting',
            'account_accountant.menu_finance_configuration_management_accounting',
        ):
            mgmt_menu = env.ref(xmlid, raise_if_not_found=False)
            if mgmt_menu:
                mgmt_menu = mgmt_menu.sudo()
                break

        if not mgmt_menu:
            config_menu = (
                env.ref('account.menu_finance_configuration', raise_if_not_found=False)
                or env.ref('account_accountant.menu_finance_configuration', raise_if_not_found=False)
            )
            domain = []
            if config_menu:
                config_menu = config_menu.sudo()
                domain.append(('parent_id', '=', config_menu.id))

            mgmt_menu = env['ir.ui.menu'].sudo().search(
                domain + [('name', 'in', ['Management', 'Gestión', 'Gestion'])],
                limit=1,
            )

        if mgmt_menu and menu.parent_id != mgmt_menu:
            menu.write({'parent_id': mgmt_menu.id})

