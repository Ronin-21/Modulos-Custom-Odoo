# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import models, fields, _
from odoo.exceptions import UserError


class SofPeriodReportWizard(models.TransientModel):
    _name = 'sof.period.report.wizard'
    _description = 'Reporte PDF por período (SOF)'

    report_type = fields.Selection([
        ('payments', 'Cobros'),
        ('sessions', 'Sesiones'),
    ], string='Reporte', required=True, default='payments')
    date_from = fields.Date(
        string='Desde', required=True,
        default=lambda self: fields.Date.today() + relativedelta(day=1),
    )
    date_to = fields.Date(string='Hasta', required=True, default=fields.Date.today)
    company_id = fields.Many2one(
        'res.company', string='Sucursal',
        default=lambda self: self.env.company,
    )

    def action_print(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('La fecha "Desde" no puede ser mayor que "Hasta".'))
        if self.report_type == 'payments':
            ref = 'sale_op_flow.action_report_sof_payments_period'
        else:
            ref = 'sale_op_flow.action_report_sof_sessions_period'
        return self.env.ref(ref).report_action(self)
