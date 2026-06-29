# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.tools.misc import formatLang


class PrsIncomeAccountReportHandler(models.AbstractModel):
    """Reporte de ingresos (liquidez) basado en extractos conciliados.

    - Toma líneas de extracto (account.bank.statement.line) con amount > 0
    - Solo conciliadas (is_reconciled = True)
    - Misma UX que el reporte de gastos: agrupado por diario + desplegable
    """

    _name = "prs.income_account_report.handler"
    _inherit = "account.report.custom.handler"
    _description = "PRS - Reporte de ingresos (extractos conciliados)"

    # ---------------------------------------------------------------------
    # Options helpers (copiado del enfoque del reporte de gastos)
    # ---------------------------------------------------------------------

    def _custom_options_initializer(self, report, options, previous_options=None):
        """Preservar el estado de desplegado y filtrar diarios a liquidez."""
        if previous_options:
            # Mantener desplegados cuando el usuario cambia filtros (mes, diarios, etc.)
            for k in ("unfolded_lines", "unfold_all"):
                if k in previous_options and k not in options:
                    options[k] = previous_options[k]
                elif k in previous_options and k in options:
                    options[k] = previous_options[k]

        # Limitar el filtro de diarios a liquidez (cash/bank) si existe la estructura esperada
        journals = options.get("journals")
        if isinstance(journals, list):
            liquidity_ids = set(self.env["account.journal"].search([("type", "in", ("cash", "bank"))]).ids)
            for node in journals:
                if isinstance(node, dict) and node.get("id") and node.get("id") not in liquidity_ids:
                    # deseleccionar y ocultar si aplica
                    node["selected"] = False

    def _get_date_range(self, options):
        date = options.get("date") or {}
        return date.get("date_from"), date.get("date_to")

    def _get_selected_journal_ids(self, options):
        journals = options.get("journals")
        if not isinstance(journals, list):
            return []
        return [j.get("id") for j in journals if isinstance(j, dict) and j.get("selected") and j.get("id")]

    def _get_partner_ids(self, options):
        # compat con diferentes estructuras de opciones
        for key in ("partner_ids", "partner_id", "partners"):
            val = options.get(key)
            if not val:
                continue
            if isinstance(val, list):
                # [1,2] o [{"id":1},...]
                ids = []
                for x in val:
                    if isinstance(x, int):
                        ids.append(x)
                    elif isinstance(x, dict) and x.get("id"):
                        ids.append(x["id"])
                if ids:
                    return ids
            if isinstance(val, dict):
                ids = val.get("ids") or val.get("partner_ids")
                if isinstance(ids, list) and ids:
                    return ids
                if isinstance(val.get("id"), int):
                    return [val["id"]]
        return []

    def _get_search_term(self, options):
        # En account_reports suele venir como "search_term" o dentro de "searchbar"
        term = options.get("search_term") or options.get("search")
        if term:
            return str(term).strip()
        searchbar = options.get("searchbar") or {}
        if isinstance(searchbar, dict):
            term = searchbar.get("search_term") or searchbar.get("term")
            if term:
                return str(term).strip()
        return ""

    def _get_unfolded_line_ids(self, options):
        unfolded = options.get("unfolded_lines")
        if isinstance(unfolded, list):
            return set(unfolded)
        return set()

    def _is_unfolded(self, options, line_id):
        return options.get("unfold_all") or (line_id in self._get_unfolded_line_ids(options))

    def _fmt_money(self, amount, options=None):
        currency = self.env.company.currency_id
        return formatLang(self.env, amount or 0.0, currency_obj=currency)

    def _blank_col(self):
        return {"name": "", "no_format": ""}

    def _line_id(self, markup, model="", value=""):
        """Build a canonical account_reports line id: `markup~model~value`.

        account_reports (Enterprise) parses line ids assuming this format.
        If we return plain strings without `~`, it can crash when it tries
        to read the markup for consolidation helpers.
        """
        return f"{markup}~{model or ''}~{value}"


    # ---------------------------------------------------------------------
    # Domain + lines
    # ---------------------------------------------------------------------

    def _build_domain(self, options):
        StatementLine = self.env["account.bank.statement.line"]
        domain = [
            ("amount", ">", 0),
        ]
        # Solo conciliados
        if "is_reconciled" in StatementLine._fields:
            domain.append(("is_reconciled", "=", True))

        # Solo diarios de liquidez
        if "journal_id" in StatementLine._fields:
            domain.append(("journal_id.type", "in", ("cash", "bank")))

        # Multicompañía
        if "company_id" in StatementLine._fields:
            domain.append(("company_id", "in", self.env.companies.ids))

        date_from, date_to = self._get_date_range(options)
        if date_from:
            domain.append(("date", ">=", date_from))
        if date_to:
            domain.append(("date", "<=", date_to))

        journal_ids = self._get_selected_journal_ids(options)
        if journal_ids:
            domain.append(("journal_id", "in", journal_ids))

        partner_ids = self._get_partner_ids(options)
        if partner_ids and "partner_id" in StatementLine._fields:
            domain.append(("partner_id", "in", partner_ids))

        term = self._get_search_term(options)
        if term:
            # OR ilike sobre campos típicos del extracto
            ors = []
            for fname in ("payment_ref", "ref", "name"):
                if fname in StatementLine._fields:
                    ors.append((fname, "ilike", term))
            if "partner_id" in StatementLine._fields:
                ors.append(("partner_id.name", "ilike", term))
                if "ref" in self.env["res.partner"]._fields:
                    ors.append(("partner_id.ref", "ilike", term))
            if ors:
                # construir OR-chain
                d = []
                for i, cond in enumerate(ors):
                    if i:
                        d.append("|")
                    d.append(cond)
                domain += d

        return domain

    def _mk_group_line(self, journal, options, amount_total):
        line_id = self._line_id("income_journal", "account.journal", journal.id)
        return {
            "id": line_id,
            "name": journal.display_name,
            "level": 1,
            "unfoldable": True,
            "unfolded": self._is_unfolded(options, line_id),
            "columns": [
                self._blank_col(),  # Fecha
                self._blank_col(),  # Cod
                self._blank_col(),  # Cliente
                {"name": journal.display_name, "no_format": journal.display_name},  # Diario
                self._blank_col(),  # Metodo
                {"name": _("Total"), "no_format": _("Total")},  # Detalle
                {"name": self._fmt_money(amount_total, options), "no_format": amount_total},  # Importe
            ],
        }

    def _mk_income_line(self, st_line, options):
        partner = st_line.partner_id if hasattr(st_line, "partner_id") else self.env["res.partner"]
        journal = st_line.journal_id if hasattr(st_line, "journal_id") else self.env["account.journal"]

        # Método: si viene de un pago, mostrar el método del pago
        method = ""
        payment = getattr(st_line, "payment_id", False)
        if payment:
            pml = getattr(payment, "payment_method_line_id", False)
            if pml:
                method = pml.name
            else:
                method = getattr(payment, "payment_method_id", False) and payment.payment_method_id.name or ""
        if not method:
            method = _("Extracto")

        # Referencia/Detalle
        ref = ""
        for fname in ("payment_ref", "ref", "name"):
            if fname in st_line._fields:
                val = (st_line[fname] or "").strip()
                if val:
                    ref = val
                    break
        if not ref and getattr(st_line, "move_id", False):
            ref = st_line.move_id.name or st_line.move_id.ref or ""
        if not ref and getattr(st_line, "statement_id", False):
            ref = st_line.statement_id.name or ""
        if not ref:
            ref = _("Ingreso")

        amount = st_line.amount or 0.0
        date = getattr(st_line, "date", False) or getattr(st_line, "create_date", False)
        date_str = date.strftime("%d/%m/%Y") if date else ""

        cust_code = partner.ref or "" if partner else ""

        line_id = self._line_id("income_line", "account.bank.statement.line", st_line.id)
        return {
            "id": line_id,
            "name": ref,  # llena la 1ra columna (evita columna en blanco)
            "level": 2,
            "parent_id": self._line_id("income_journal", "account.journal", journal.id) if journal else None,
            "columns": [
                {"name": date_str, "no_format": date_str},
                {"name": cust_code, "no_format": cust_code},
                {"name": partner.display_name if partner else "", "no_format": partner.display_name if partner else ""},
                {"name": journal.display_name if journal else "", "no_format": journal.display_name if journal else ""},
                {"name": method, "no_format": method},
                {"name": ref, "no_format": ref},
                {"name": self._fmt_money(amount, options), "no_format": amount},
            ],
        }

    def _mk_total_line(self, options, amount_total):
        return {
            "id": self._line_id("total", "", "prs_income_total"),
            "name": _("TOTAL GENERAL"),
            "level": 0,
            "columns": [
                self._blank_col(),
                self._blank_col(),
                self._blank_col(),
                self._blank_col(),
                self._blank_col(),
                {"name": _("TOTAL GENERAL"), "no_format": _("TOTAL GENERAL")},
                {"name": self._fmt_money(amount_total, options), "no_format": amount_total},
            ],
        }

    @api.model
    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals=None, warnings=None):
        StatementLine = self.env["account.bank.statement.line"]

        domain = self._build_domain(options)
        st_lines = StatementLine.search(domain, order="journal_id, date, id")

        # agrupar por diario
        by_journal = {}
        for l in st_lines:
            jid = l.journal_id.id if getattr(l, "journal_id", False) else 0
            by_journal.setdefault(jid, []).append(l)

        lines = []
        grand_total = 0.0

        journals = self.env["account.journal"].browse([jid for jid in by_journal.keys() if jid])
        journals = journals.sorted(key=lambda j: (j.sequence, j.name))

        for journal in journals:
            items = by_journal.get(journal.id, [])
            journal_total = sum((x.amount or 0.0) for x in items)
            grand_total += journal_total

            group_line = self._mk_group_line(journal, options, journal_total)
            lines.append((0, group_line))

            if group_line["unfolded"]:
                for l in items:
                    lines.append((0, self._mk_income_line(l, options)))

        # total general
        lines.append((0, self._mk_total_line(options, grand_total)))
        return lines
