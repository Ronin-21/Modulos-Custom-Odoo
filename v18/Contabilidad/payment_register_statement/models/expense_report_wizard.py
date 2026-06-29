# -*- coding: utf-8 -*-
import json
import logging

from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class PrsExpenseReportWizard(models.TransientModel):
    _name = "prs.expense.report.wizard"
    _description = "Wizard - Reporte de gastos / compras"

    domain_text = fields.Text(string="Dominio", readonly=True)

    group_mode = fields.Selection(
        selection=[
            ("concept", "Agrupar por concepto"),
            ("date", "Solo por fecha"),
        ],
        string="Vista",
        required=True,
        default="concept",
    )

    order = fields.Selection(
        selection=[("asc", "Fecha ascendente"), ("desc", "Fecha descendente")],
        string="Orden",
        required=True,
        default="asc",
    )

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        default=lambda self: self.env.company,
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        related="company_id.currency_id",
        readonly=True,
    )

    payment_count = fields.Integer(string="Pagos", compute="_compute_summary")
    total_amount = fields.Monetary(string="Total", currency_field="currency_id", compute="_compute_summary")
    date_from = fields.Date(string="Desde", compute="_compute_summary")
    date_to = fields.Date(string="Hasta", compute="_compute_summary")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = dict(self.env.context or {})
        active_domain = ctx.get("active_domain") or []
        # Guardamos el dominio como texto (repr) para poder re-usarlo desde el reporte.
        try:
            res["domain_text"] = repr(active_domain)
        except Exception:
            res["domain_text"] = "[]"
        return res

    def _get_domain(self):
        self.ensure_one()
        txt = (self.domain_text or "[]").strip()
        if not txt:
            return []
        # Acepta tanto repr(list/tuple) como JSON.
        try:
            if txt.startswith("[") and ("'" not in txt) and ('"' in txt):
                return json.loads(txt)
        except Exception:
            pass
        try:
            dom = safe_eval(txt, {"__builtins__": {}})
            return dom if isinstance(dom, (list, tuple)) else []
        except Exception:
            _logger.exception("PRS: No se pudo parsear domain_text del reporte de gastos")
            return []

    def _get_payments(self):
        self.ensure_one()
        domain = self._get_domain()
        # Por seguridad, si el dominio no limita tipo de pago, lo forzamos a outbound
        if not any(isinstance(d, (list, tuple)) and len(d) >= 1 and d[0] == "payment_type" for d in domain):
            domain = list(domain) + [("payment_type", "=", "outbound")]
        payments = self.env["account.payment"].search(domain, order=f"date {self.order}, id {self.order}")
        return payments

    @api.depends("domain_text", "order")
    def _compute_summary(self):
        for wiz in self:
            payments = wiz._get_payments() if wiz.domain_text is not None else self.env["account.payment"]
            wiz.payment_count = len(payments)
            wiz.total_amount = sum(payments.mapped("amount")) if payments else 0.0
            dates = payments.mapped("date") if payments else []
            wiz.date_from = min(dates) if dates else False
            wiz.date_to = max(dates) if dates else False

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref("payment_register_statement.action_report_prs_expenses_pdf").report_action(self)
