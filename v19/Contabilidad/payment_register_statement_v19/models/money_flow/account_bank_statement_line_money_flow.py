# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    prs_money_flow_id = fields.Many2one(
        'prs.money.flow',
        string='Flujo de dinero PRS',
        readonly=True,
        index=True,
        ondelete='set null',
    )
