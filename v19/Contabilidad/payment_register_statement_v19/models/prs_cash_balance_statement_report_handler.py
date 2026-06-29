# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.osv import expression
from odoo.tools.misc import format_date

from .prs_expense_account_report_handler import PrsExpenseAccountReportHandler


class PrsCashBalanceStatementReportHandler(models.AbstractModel):
    _name = "prs.cash_balance_statement_report.handler"
    _inherit = "prs.expense_account_report.handler"
    _description = "PRS Cash Balance by Reconciled Statement Lines (Custom Handler)"

    # ------------------------------------------------------------
    # DOMAIN (statement lines)
    # ------------------------------------------------------------
    def _build_domain(self, options):
        Line = self.env["account.bank.statement.line"]
        domain = []
        journal_field = "journal_id" if "journal_id" in Line._fields else "statement_id.journal_id"

        # Date range
        date_from, date_to = self._get_date_range(options)
        date_field = "date" if "date" in Line._fields else "statement_id.date"
        if date_from:
            domain.append((date_field, ">=", date_from))
        if date_to:
            domain.append((date_field, "<=", date_to))

        # Partner filter
        partner_ids = self._get_partner_ids(options)
        if partner_ids and "partner_id" in Line._fields:
            domain.append(("partner_id", "in", partner_ids))

        # Search term
        term = self._get_search_term(options)
        if term:
            ors = []
            for fname in ("payment_ref", "ref", "name"):
                if fname in Line._fields:
                    ors.append((fname, "ilike", term))
            ors.append(("partner_id.name", "ilike", term))
            if ors:
                d = []
                for i, cond in enumerate(ors):
                    if i == 0:
                        d.append(cond)
                    else:
                        d = ["|", cond] + d
                domain += d

        # Journals (liquidity only)
        liq_ids = self._get_liquidity_journal_ids()
        journal_ids = []
        if liq_ids:
            journal_ids = self._get_selected_journal_ids(options, liq_ids)

        if not journal_ids:
            return domain

        journals = self.env["account.journal"].browse(journal_ids).exists()
        reconciled_only_ids = set(journals.filtered(lambda j: getattr(j, "prs_only_reconciled_statements", False)).ids)
        normal_ids = set(journal_ids) - reconciled_only_ids

        if reconciled_only_ids and normal_ids:
            normal_domain = [(journal_field, "in", sorted(normal_ids))]
            if "is_reconciled" in Line._fields:
                reconciled_domain = [(journal_field, "in", sorted(reconciled_only_ids)), ("is_reconciled", "=", True)]
            elif "move_id" in Line._fields:
                reconciled_domain = [(journal_field, "in", sorted(reconciled_only_ids)), ("move_id", "!=", False)]
            else:
                reconciled_domain = [(journal_field, "in", sorted(reconciled_only_ids))]
            domain = expression.AND([domain, expression.OR([normal_domain, reconciled_domain])])
        elif reconciled_only_ids:
            domain.append((journal_field, "in", sorted(reconciled_only_ids)))
            if "is_reconciled" in Line._fields:
                domain.append(("is_reconciled", "=", True))
            elif "move_id" in Line._fields:
                domain.append(("move_id", "!=", False))
        else:
            domain.append((journal_field, "in", sorted(normal_ids)))

        return domain

    # ------------------------------------------------------------
    # LINE BUILDERS
    # ------------------------------------------------------------
    def _mk_stmt_line(self, l, options, level=2):
        amount = getattr(l, "amount", 0.0) or 0.0
        income = amount if amount > 0 else 0.0
        expense = (-amount) if amount < 0 else 0.0

        dt = getattr(l, "date", False) or getattr(getattr(l, "statement_id", False), "date", False)
        journal = getattr(l, "journal_id", False) or getattr(getattr(l, "statement_id", False), "journal_id", False)
        statement = getattr(l, "statement_id", False)
        partner = getattr(l, "partner_id", False)

        partner_name = partner.display_name if partner else ""
        statement_name = statement.display_name if statement else ""

        ref = ""
        for fname in ("payment_ref", "ref", "name"):
            if hasattr(l, fname):
                val = getattr(l, fname) or ""
                if val:
                    ref = val
                    break

        detail = getattr(l, "narration", "") if hasattr(l, "narration") else ""
        if not detail:
            detail = getattr(l, "note", "") if hasattr(l, "note") else ""
        if not detail and getattr(l, "payment_id", False):
            detail = getattr(l.payment_id, "ref", "") or getattr(l.payment_id, "communication", "") or ""

        cols = [
            {"name": format_date(self.env, dt) if dt else "", "no_format": dt or ""},
            {"name": journal.display_name if journal else "", "no_format": journal.display_name if journal else ""},
            {"name": statement.display_name if statement else "", "no_format": statement.display_name if statement else ""},
            {"name": ref, "no_format": ref},
            {"name": partner.display_name if partner else "", "no_format": partner.display_name if partner else ""},
            {"name": detail or "", "no_format": detail or ""},
            {"name": self._fmt_money(income, options), "no_format": income},
            {"name": self._fmt_money(expense, options), "no_format": expense},
            {"name": self._fmt_money(amount, options), "no_format": amount},
        ]

        return {
            "id": self._line_id("stmt_line", "account.bank.statement.line", l.id),
            "name": ref or detail or partner_name or statement_name or (journal.display_name if journal else ""),
            "level": level,
            "class": "prs_cash_balance_line",
            "columns": cols,
            "caret_options": "account.bank.statement.line",
        }

    def _mk_total_line(self, tot_in, tot_out, options):
        net = tot_in - tot_out
        return {
            "id": self._line_id("total", "", "cash_balance"),
            "name": _("TOTAL"),
            "level": 1,
            "class": "prs_cash_balance_total",
            "columns": [{"name": ""} for _ in range(6)] + [
                {"name": self._fmt_money(tot_in, options), "no_format": tot_in},
                {"name": self._fmt_money(tot_out, options), "no_format": tot_out},
                {"name": self._fmt_money(net, options), "no_format": net},
            ],
        }

    def _mk_ui_header_line(self, options):
        """Workaround UI: mostrar títulos como primera línea (solo en pantalla).
        El PDF/XLSX ya muestra correctamente los encabezados.
        """
        return {
            "id": self._line_id("ui_header", "", "cash_balance"),
            "name": "",
            "level": 0,
            "columns": [
                {"name": "Fecha", "no_format": "Fecha"},
                {"name": "Diario", "no_format": "Diario"},
                {"name": "Estado de cuenta", "no_format": "Estado de cuenta"},
                {"name": "Referencia", "no_format": "Referencia"},
                {"name": "Contacto", "no_format": "Contacto"},
                {"name": "Detalle", "no_format": "Detalle"},
                {"name": "Ingresos", "no_format": "Ingresos"},
                {"name": "Egresos", "no_format": "Egresos"},
                {"name": "Balance", "no_format": "Balance"},
            ],
            "class": "text-muted",
        }

    # ------------------------------------------------------------
    # MAIN GENERATOR (ordered by date)
    # ------------------------------------------------------------
    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals=None, warnings=None):
        Line = self.env["account.bank.statement.line"]
        domain = self._build_domain(options)

        order = "date, id" if "date" in Line._fields else "statement_id.date, id"
        lines_rs = Line.search(domain, order=order)

        lines = []

        if not self._prs_is_export(options):
            lines.append((0, self._mk_ui_header_line(options)))

        tot_in = 0.0
        tot_out = 0.0

        for l in lines_rs:
            amount = getattr(l, "amount", 0.0) or 0.0
            if amount > 0:
                tot_in += amount
            elif amount < 0:
                tot_out += (-amount)
            lines.append((0, self._mk_stmt_line(l, options, level=2)))

        lines.append((0, self._mk_total_line(tot_in, tot_out, options)))
        return lines
