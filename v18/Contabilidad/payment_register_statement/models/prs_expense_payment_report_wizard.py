# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class PrsExpensePaymentReportWizard(models.TransientModel):
    _name = "prs.expense.payment.report.wizard"
    _description = "Reporte de Gastos / Compras (Pagos)"

    date_from = fields.Date(string="Desde")
    date_to = fields.Date(string="Hasta")

    # NOTE: Odoo genera el nombre de la tabla rel automáticamente y en SH puede superar el límite
    # de PostgreSQL (63 chars). Fijamos nombres cortos para evitar "Table name ... is too long".
    journal_ids = fields.Many2many(
        comodel_name="account.journal",
        relation="prs_exp_rpt_wiz_journal_rel",
        column1="wizard_id",
        column2="journal_id",
        string="Diarios",
    )
    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="prs_exp_rpt_wiz_partner_rel",
        column1="wizard_id",
        column2="partner_id",
        string="Proveedores",
        domain=[("supplier_rank", ">", 0)],
    )
    payment_method_line_ids = fields.Many2many(
        comodel_name="account.payment.method.line",
        relation="prs_exp_rpt_wiz_pml_rel",
        column1="wizard_id",
        column2="payment_method_line_id",
        string="Métodos de pago",
    )
    expense_concept_ids = fields.Many2many(
        comodel_name="prs.expense.concept",
        relation="prs_exp_rpt_wiz_concept_rel",
        column1="wizard_id",
        column2="concept_id",
        string="Conceptos de gasto",
    )

    prs_is_misc_expense = fields.Selection(
        [("all", "Todos"), ("yes", "Solo Gastos Varios"), ("no", "Excluir Gastos Varios")],
        string="Gastos Varios",
        default="all",
        required=True,
    )

    group_by = fields.Selection(
        [("date", "Fecha"), ("concept_date", "Concepto y Fecha")],
        string="Agrupar por",
        default="concept_date",
        required=True,
    )

    include_unposted = fields.Boolean(string="Incluir no publicados", default=False)

    def _base_domain(self):
        domain = [("partner_type", "=", "supplier")]
        if not self.include_unposted:
            domain.append(("state", "=", "posted"))
        return domain

    def _filters_domain(self):
        self.ensure_one()
        domain = list(self._base_domain())

        if self.date_from:
            domain.append(("date", ">=", self.date_from))
        if self.date_to:
            domain.append(("date", "<=", self.date_to))

        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))
        if self.partner_ids:
            domain.append(("partner_id", "in", self.partner_ids.ids))
        if self.payment_method_line_ids:
            domain.append(("payment_method_line_id", "in", self.payment_method_line_ids.ids))
        if self.expense_concept_ids:
            domain.append(("prs_expense_concept_id", "in", self.expense_concept_ids.ids))

        if self.prs_is_misc_expense == "yes":
            domain.append(("prs_is_misc_expense", "=", True))
        elif self.prs_is_misc_expense == "no":
            domain.append(("prs_is_misc_expense", "=", False))

        return domain

    def action_open_list(self):
        # Open account.payment list with same filters (Excel export is built-in)
        self.ensure_one()
        domain = self._filters_domain()

        action = self.env.ref("account.action_account_payments").sudo().read()[0]
        action.update({
            "name": _("Reporte de Gastos / Compras"),
            "domain": domain,
            "context": dict(self.env.context),
        })

        if self.group_by == "concept_date":
            action["context"].update({"search_default_group_by_prs_expense_concept": 1})

        # If our dedicated views exist, use them
        try:
            list_view = self.env.ref("payment_register_statement.view_prs_expense_payment_report_list")
            search_view = self.env.ref("payment_register_statement.view_prs_expense_payment_report_search")
            action["views"] = [(list_view.id, "list"), (False, "form")]
            action["search_view_id"] = search_view.id
        except Exception:
            pass

        return action

    def action_print_pdf(self):
        self.ensure_one()
        payments = self.env["account.payment"].search(self._filters_domain(), order="date asc, id asc")
        if not payments:
            raise UserError(_("No hay pagos que coincidan con los filtros seleccionados."))
        data = {
            "wizard_id": self.id,
            "group_by": self.group_by,
            "date_from": self.date_from and fields.Date.to_string(self.date_from) or False,
            "date_to": self.date_to and fields.Date.to_string(self.date_to) or False,
        }
        return self.env.ref("payment_register_statement.action_report_prs_expense_payments").report_action(payments, data=data)
