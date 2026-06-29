# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError


class AccountReport(models.Model):
    _inherit = 'account.report'

    def _report_custom_engine_lb_kpi_ndays(
        self, expressions, options, date_scope, current_groupby, next_groupby,
        offset=0, limit=None, warnings=None,
    ):
        """Cantidad de días en el rango de fechas seleccionado."""
        if current_groupby or next_groupby:
            raise UserError(self.env._("El indicador de días no soporta agrupamiento."))
        date_diff = (
            fields.Date.from_string(options['date']['date_to'])
            - fields.Date.from_string(options['date']['date_from'])
        )
        return {'result': date_diff.days}
