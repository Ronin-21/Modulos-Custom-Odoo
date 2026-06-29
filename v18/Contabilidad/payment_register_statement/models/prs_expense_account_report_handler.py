# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.tools.misc import formatLang, format_date

import re


class PrsExpenseAccountReportHandler(models.AbstractModel):
    _name = "prs.expense_account_report.handler"
    _inherit = "account.report.custom.handler"
    _description = "PRS Expense Account Report (Custom Handler)"

    # ------------------------------------------------------------
    # OPTIONS
    # ------------------------------------------------------------
    def _custom_options_initializer(self, report, options, previous_options=None):
        """Hook called by account_reports to initialize report options.

        NOTE: In some account_reports versions, the core initializer can overwrite the
        current RPC options with values from previous_options. That breaks dynamic
        unfold/fold (the UI only reflects the change after a full page reload).
        We therefore preserve unfolded state coming from the current options payload.
        """
        # Defensive: some edge calls can pass options as None.
        if options is None:
            options = {}

        # Preserve current unfold state (coming from the web client).
        _unfolded_lines_in = options.get("unfolded_lines")
        _unfold_all_in = options.get("unfold_all")

        # Super does in-place initialization and returns None in many versions.
        super()._custom_options_initializer(report, options, previous_options=previous_options)

        # Restore unfold state if it was provided by the current options payload.
        if _unfolded_lines_in is not None:
            options["unfolded_lines"] = _unfolded_lines_in
        if _unfold_all_in is not None:
            options["unfold_all"] = _unfold_all_in


        # Defensive: some edge calls can pass options as None.
        if options is None:
            options = {}

        # Default grouping mode (we keep it internal for now; later we can expose it with a button if needed)
        options.setdefault("prs_group_mode", (previous_options or {}).get("prs_group_mode") or "concept")

        # Extra filters (backend-ready; UI can be added later without changing the report logic).
        options.setdefault("prs_payment_method_line_id", (previous_options or {}).get("prs_payment_method_line_id") or False)
        options.setdefault("prs_expense_concept_id", (previous_options or {}).get("prs_expense_concept_id") or False)
        options.setdefault("prs_only_misc_expense", bool((previous_options or {}).get("prs_only_misc_expense")))

        # Disable comparison columns by default to avoid duplicated "Fecha/Proveedor/..." columns in PDF/HTML.
        comp = options.get("comparison")
        if isinstance(comp, dict):
            comp["filter"] = False
            comp["periods"] = []
            comp["number_period"] = 0
        # Journals filter: handled after core option build in account.report.get_options (see models/account_report.py)
        # PRS: Force full tree in HTML so caret fold/unfold can work without a full page reload.
        # This keeps all children lines available in the DOM; the JS layer then handles showing/hiding.
        if not self._prs_is_export(options):
            options['unfold_all'] = True

        return options

    def _get_liquidity_journal_ids(self):
        # In multi-company, record rules use allowed_company_ids (active companies). If the user runs the
        # report with a different set of active companies, the selector could become empty. We therefore
        # search in ALL companies the user has access to.
        allowed_company_ids = self.env.user.company_ids.ids
        Journal = self.env["account.journal"].with_context(allowed_company_ids=allowed_company_ids)
        return set(Journal.search([("type", "in", ("bank", "cash"))]).ids)

    # ---------------------------------------------------------------------
    # Journals filter: keep native dropdown, but restrict to liquidity journals
    # ---------------------------------------------------------------------
    def _coerce_int(self, value):
        """Best-effort coercion to int for ids coming from account_reports widgets."""
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            nums = re.findall(r"\d+", value)
            return int(nums[-1]) if nums else None
        if isinstance(value, (list, tuple)) and value:
            return self._coerce_int(value[-1])
        if isinstance(value, dict):
            # sometimes widgets nest the actual id in {id:..} or {res_id:..}
            for k in ("id", "res_id", "journal_id"):
                v = value.get(k)
                coerced = self._coerce_int(v)
                if coerced:
                    return coerced
        return None

    def _iter_journal_nodes(self, nodes):
        """Yield all leaf journal nodes from the journals option tree."""
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            children = node.get("children")
            if isinstance(children, list) and children:
                yield from self._iter_journal_nodes(children)
                continue
            if node.get("model") == "account.journal":
                yield node

    def _extract_selected_journal_ids(self, journals_nodes):
        """Return selected journal ids from options['journals'] (tree or flat)."""
        leaves = list(self._iter_journal_nodes(journals_nodes or []))
        # If no leaves, try a flat list format
        if not leaves and isinstance(journals_nodes, list):
            for n in journals_nodes:
                if isinstance(n, dict) and n.get("model") == "account.journal":
                    leaves.append(n)

        ids_all = []
        ids_sel = []
        for node in leaves:
            jid = self._coerce_int(node.get("id")) or self._coerce_int(node.get("res_id")) or self._coerce_int(node.get("journal_id"))
            if jid:
                ids_all.append(jid)
                if node.get("selected") is True:
                    ids_sel.append(jid)

        return ids_sel or ids_all

    def _apply_liquidity_journal_filter(self, options, previous_options=None):
        """Restrict the Journals dropdown to liquidity journals (bank/cash) while keeping native structure."""
        if not options or not options.get("journals"):
            return

        liquidity_ids = set(self.env["account.journal"].search([
            ("type", "in", ("bank", "cash")),
            ("company_id", "in", self.env.companies.ids),
        ]).ids)

        def _extract_id(node):
            for key in ("id", "res_id", "journal_id"):
                val = (node or {}).get(key)
                jid = self._coerce_int(val)
                if jid:
                    return jid
            return None

        def _filter(nodes):
            res = []
            for node in nodes or []:
                if not isinstance(node, dict):
                    res.append(node)
                    continue
                children = node.get("children")
                if isinstance(children, list) and children:
                    node2 = dict(node)
                    node2["children"] = _filter(children)
                    # Keep group nodes even if children became empty? better drop empties to avoid blank groups.
                    if node2["children"]:
                        res.append(node2)
                    continue
                if node.get("model") == "account.journal":
                    jid = _extract_id(node)
                    if jid in liquidity_ids:
                        res.append(node)
                else:
                    # non-journal leaf (rare) keep
                    res.append(node)
            return res

        options["journals"] = _filter(options["journals"])
    def _filter_journal_options_in_place(self, options, allowed_journal_ids):
        journals_opt = options.get("journals")
        if not isinstance(journals_opt, list):
            return

        if not allowed_journal_ids:
            return

        # account_reports may provide journals as grouped entries with children
        grouped = any(isinstance(j, dict) and isinstance(j.get("children"), list) for j in journals_opt)

        if grouped:
            new_groups = []
            for group in journals_opt:
                if not isinstance(group, dict) or not isinstance(group.get("children"), list):
                    continue
                children = group.get("children", [])
                new_children = [c for c in children if isinstance(c, dict) and c.get("id") in allowed_journal_ids]
                if new_children:
                    g = dict(group)
                    g["children"] = new_children
                    new_groups.append(g)
            options["journals"] = new_groups
        else:
            # Flat list
            options["journals"] = [j for j in journals_opt if isinstance(j, dict) and j.get("id") in allowed_journal_ids]

        # Fallback: if we filtered everything out, rebuild a minimal flat list.
        if not options.get("journals"):
            journals = self.env["account.journal"].browse(sorted(allowed_journal_ids)).exists()
            options["journals"] = [{"id": j.id, "name": j.display_name, "selected": True} for j in journals]


    # ------------------------------------------------------------
    # DOMAIN HELPERS
    # ------------------------------------------------------------
    def _get_date_range(self, options):
        date_opt = options.get("date") or {}
        date_from = date_opt.get("date_from") or options.get("date_from")
        date_to = date_opt.get("date_to") or options.get("date_to")
        return date_from, date_to

    def _get_partner_ids(self, options):
        # account_reports uses multiple formats depending on version/widgets.
        for key in ("partner_ids", "partner_id", "partners"):
            val = options.get(key)
            if isinstance(val, list) and val:
                # list of ids
                if all(isinstance(x, int) for x in val):
                    return val
                # list of dicts
                if all(isinstance(x, dict) for x in val):
                    ids = [x.get("id") for x in val if isinstance(x.get("id"), int)]
                    if ids:
                        return ids
            if isinstance(val, int):
                return [val]
        # Some versions store it under options['partner'] = {'ids': [...]}
        p = options.get("partner")
        if isinstance(p, dict):
            ids = p.get("ids") or p.get("partner_ids")
            if isinstance(ids, list) and ids and all(isinstance(x, int) for x in ids):
                return ids
        return []

    def _get_selected_journal_ids(self, options, allowed_journal_ids):
        """Return selected journal ids, always restricted to liquidity journals."""
        journals_nodes = (options or {}).get("journals") or []
        ids = self._extract_selected_journal_ids(journals_nodes)
        ids = [jid for jid in ids if jid in allowed_journal_ids]
        return ids or sorted(allowed_journal_ids)

    def _get_search_term(self, options):
        # account_reports search bar stores it as "search_term" in options
        term = (options.get("search_term") or "").strip()
        return term or None

    def _build_domain(self, options):
        Payment = self.env["account.payment"]
        domain = []

        # Expenses: vendor payments / outbound.
        if "payment_type" in Payment._fields:
            domain.append(("payment_type", "=", "outbound"))

        # Date range
        date_from, date_to = self._get_date_range(options)
        if date_from:
            domain.append(("date", ">=", date_from))
        if date_to:
            domain.append(("date", "<=", date_to))

        # Journals (liquidity only). If we can't detect any liquidity journals (company context...),
        # we DO NOT force an empty domain, otherwise the report will show nothing and the dropdown...
        liq_ids = self._get_liquidity_journal_ids()
        if liq_ids:
            journal_ids = self._get_selected_journal_ids(options, liq_ids)
            # Same protection: never force an empty "in" domain.
            if journal_ids:
                domain.append(("journal_id", "in", journal_ids))

        # Partner filter (Contacto)
        partner_ids = self._get_partner_ids(options)
        if partner_ids and "partner_id" in Payment._fields:
            domain.append(("partner_id", "in", partner_ids))

        # Custom filters
        if options.get("prs_payment_method_line_id") and "payment_method_line_id" in Payment._fields:
            domain.append(("payment_method_line_id", "=", int(options["prs_payment_method_line_id"])))
        concept_opt = options.get("prs_expense_concept_id") or options.get("prs_concept_id")
        if concept_opt and "prs_expense_concept_id" in Payment._fields:
            domain.append(("prs_expense_concept_id", "=", int(concept_opt)))
        if options.get("prs_only_misc_expense") and "prs_is_misc_expense" in Payment._fields:
            domain.append(("prs_is_misc_expense", "=", True))

        # Optional: ignore cancelled payments if the field exists
        if "state" in Payment._fields:
            # We keep ALL non-cancelled states so "En proceso" works.
            domain.append(("state", "not in", ("cancel", "cancelled")))

        # Search bar
        term = self._get_search_term(options)
        if term:
            or_domain = []
            if "name" in Payment._fields:
                or_domain.append(("name", "ilike", term))
            if "memo" in Payment._fields:
                or_domain.append(("memo", "ilike", term))
            if "communication" in Payment._fields:
                or_domain.append(("communication", "ilike", term))
            if "ref" in Payment._fields:
                or_domain.append(("ref", "ilike", term))
            # partner name
            or_domain.append(("partner_id.name", "ilike", term))

            # Build OR chain
            if or_domain:
                # Convert [a,b,c] to ['|','|',a,b,c]
                dom = []
                for _ in range(len(or_domain) - 1):
                    dom.append("|")
                dom.extend(or_domain)
                domain.extend(dom)

        return domain

    # ------------------------------------------------------------
    # LINE BUILDERS
    # ------------------------------------------------------------
    def _line_id(self, markup, model="", value=""):
        """Build a report line id.

        Keep the canonical `markup~model~id` format used by account_reports.
        Using a real model name + integer id (when possible) makes the unfold
        toggling more reliable across Odoo versions.
        """
        return f"{markup}~{model or ''}~{value}"

    # ------------------------------------------------------------
    # RENDER MODE HELPERS
    # ------------------------------------------------------------
    def _prs_is_export(self, options):
        """Return True when account_reports is generating export/print output."""
        if not isinstance(options, dict):
            return False
        # Various versions use different flags/keys.
        if options.get('export_mode') or options.get('print_mode'):
            return True
        out = options.get('output_format') or options.get('export_type')
        if out in ('pdf', 'xlsx', 'csv'):
            return True
        # Some versions set file_export_type.
        if options.get('file_export_type'):
            return True
        return False

    def _prs_force_full_tree(self, options):
        """When True, force foldable lines to be *unfolded* server-side.

        This prevents server-side pruning of descendant lines. Then a small JS
        fallback can hide/show descendants immediately on click, without requiring
        a full report reload.
        """
        return not self._prs_is_export(options)

    def _get_unfolded_line_ids(self, options):
        """Extract unfolded line ids from options (Odoo 18+).

        The web client can send:
          - list[str]
          - dict {line_id: true/false}
          - dict per column-group {cg_key: {line_id: true/false}}
        We must only treat ids explicitly marked True as unfolded.
        """
        if not isinstance(options, dict):
            return set()

        if options.get("unfold_all"):
            return {"__ALL__"}

        payloads = []
        for key in ("unfolded_lines", "unfolded_line_ids", "unfolded_lines_ids", "unfolded_line_id"):
            val = options.get(key)
            if val:
                payloads.append(val)

        unfolded = set()

        def _add_from(val):
            if not val:
                return
            if isinstance(val, (list, tuple, set)):
                for x in val:
                    if isinstance(x, str):
                        unfolded.add(x)
                return
            if isinstance(val, str):
                parts = [p.strip() for p in val.split(",") if p.strip()]
                for p in parts:
                    unfolded.add(p)
                return
            if isinstance(val, dict):
                # {line_id: bool}
                if val and all(isinstance(v, bool) for v in val.values()):
                    for k, v in val.items():
                        if v and isinstance(k, str):
                            unfolded.add(k)
                    return
                # per column-group mapping or nested dict
                for v in val.values():
                    _add_from(v)
                return

        for p in payloads:
            _add_from(p)

        return unfolded

    def _is_unfolded(self, options, line_id):
        if not line_id or not isinstance(options, dict):
            return False
        unfolded = self._get_unfolded_line_ids(options)
        return ("__ALL__" in unfolded) or (line_id in unfolded)

    def _fmt_money(self, amount, options):
        currency = self.env.company.currency_id
        return formatLang(self.env, amount, currency_obj=currency)

    def _payment_method_name(self, p):
        if hasattr(p, "payment_method_line_id") and p.payment_method_line_id:
            return p.payment_method_line_id.display_name
        if hasattr(p, "payment_method_id") and p.payment_method_id:
            return p.payment_method_id.display_name
        return ""

    def _payment_detail(self, p):
        parts = []
        # memo / communication
        for f in ("memo", "communication", "ref"):
            if hasattr(p, f):
                val = getattr(p, f) or ""
                if val and val not in parts:
                    parts.append(val)
                    break

        # Linked documents (reconciled invoices/bills)
        # In Odoo, payment has reconciled_invoice_ids (customer) and reconciled_bill_ids (vendor)
        doc_names = []
        if hasattr(p, "reconciled_bill_ids") and p.reconciled_bill_ids:
            doc_names += [m.name for m in p.reconciled_bill_ids if m.name]
        if hasattr(p, "reconciled_invoice_ids") and p.reconciled_invoice_ids:
            doc_names += [m.name for m in p.reconciled_invoice_ids if m.name]
        doc_names = list(dict.fromkeys(doc_names))  # unique preserving order
        if doc_names:
            parts.append(", ".join(doc_names))

        return " | ".join([x for x in parts if x]) or ""

    def _get_payment_related_moves(self, p):
        """Return account.move records reconciled with this payment (bills/invoices)."""
        Move = self.env["account.move"]
        moves = Move.browse()
        if hasattr(p, "reconciled_bill_ids") and p.reconciled_bill_ids:
            moves |= p.reconciled_bill_ids
        if hasattr(p, "reconciled_invoice_ids") and p.reconciled_invoice_ids:
            moves |= p.reconciled_invoice_ids
        return moves

    def _mk_group_line(self, group_key, label, level=2):
        return {
            "id": self._line_id("group", "", group_key),
            "name": label,
            "level": level,
            "columns": [{"name": ""} for _ in range(7)],
            "unfoldable": False,
            "unfolded": False,
        }

    def _mk_payment_line(self, p, parent_id, options, level=3, unfoldable=False, unfolded=False):
        # amount: show as positive expense
        amount = getattr(p, "amount", 0.0) or 0.0

        cols = [
            {"name": format_date(self.env, p.date) if getattr(p, "date", False) else "", "no_format": getattr(p, "date", False) or ""},
            {"name": (p.partner_id.ref or "") if getattr(p, "partner_id", False) else "", "no_format": (p.partner_id.ref or "") if getattr(p, "partner_id", False) else ""},
            {"name": p.partner_id.display_name if getattr(p, "partner_id", False) else "", "no_format": p.partner_id.display_name if getattr(p, "partner_id", False) else ""},
            {"name": p.journal_id.display_name if getattr(p, "journal_id", False) else "", "no_format": p.journal_id.display_name if getattr(p, "journal_id", False) else ""},
            {"name": self._payment_method_name(p), "no_format": self._payment_method_name(p)},
            {"name": self._payment_detail(p), "no_format": self._payment_detail(p)},
            {"name": self._fmt_money(amount, options), "no_format": amount},
        ]

        return {
            "id": self._line_id("payment", "account.payment", p.id),
            "name": p.name or p.display_name or "",
            "level": level,
            "class": "prs_expense_line prs_payment_line" + (" prs_foldable" if unfoldable else ""),
            "parent_id": parent_id,
            "columns": cols,
            "caret_options": "account.payment",
            # Allow drilling down (optional) to linked invoices/bills.
            "unfoldable": bool(unfoldable),
            "unfolded": bool(unfolded),
            # Make the line label clickable (open payment).
            "action": {
                "type": "ir.actions.act_window",
                "res_model": "account.payment",
                "res_id": p.id,
                "views": [(False, "form")],
            },
        }

    def _mk_move_ref_line(self, move, parent_id, options, level=4):
        """A child line showing a linked invoice/bill reference, clickable."""
        move_date = getattr(move, "invoice_date", False) or getattr(move, "date", False)
        partner = getattr(move, "partner_id", False)
        journal = getattr(move, "journal_id", False)

        label = move.name or getattr(move, "ref", "") or move.display_name or ""

        cols = [
            {"name": format_date(self.env, move_date) if move_date else "", "no_format": move_date or ""},
            {"name": (partner.ref or "") if partner else "", "no_format": (partner.ref or "") if partner else ""},
            {"name": partner.display_name if partner else "", "no_format": partner.display_name if partner else ""},
            {"name": journal.display_name if journal else "", "no_format": journal.display_name if journal else ""},
            {"name": "", "no_format": ""},
            {"name": label, "no_format": label},
            {"name": "", "no_format": 0.0},
        ]

        return {
            "id": self._line_id("move", "account.move", move.id),
            "name": "↳ " + label,
            "level": level,
            "class": "prs_expense_line prs_move_line",
            "parent_id": parent_id,
            "columns": cols,
            "caret_options": "account.move",
            "action": {
                "type": "ir.actions.act_window",
                "res_model": "account.move",
                "res_id": move.id,
                "views": [(False, "form")],
            },
        }


    def _mk_group_total_line(self, label, total_amount, parent_id, options, level=3, group_key="subtotal"):
        """Subtotal line for a group (shown at the bottom of that group)."""
        cols = [{"name": ""} for _ in range(6)] + [{"name": self._fmt_money(total_amount, options), "no_format": total_amount}]
        return {
            "id": self._line_id("subtotal", "", group_key),
            "name": _("TOTAL %s") % (label or ""),
            "level": level,
            "class": "prs_expense_line prs_group_total_line",
            "parent_id": parent_id,
            "columns": cols,
        }

    def _mk_total_line(self, total_amount, options):
        return {
            "id": self._line_id("total", "", "general"),
            "name": _("TOTAL GENERAL"),
            "level": 1,
            "class": "prs_expense_line prs_total_line",
            "columns": [{"name": ""} for _ in range(6)] + [{"name": self._fmt_money(total_amount, options), "no_format": total_amount}],
        }

    # ------------------------------------------------------------
    # MAIN GENERATOR
    # ------------------------------------------------------------
    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        domain = self._build_domain(options)
        Payment = self.env["account.payment"]
        payments = Payment.search(domain, order="date, id")

        # Grouping
        group_mode = options.get("prs_group_mode") or "concept"
        groups = {}

        for p in payments:
            if group_mode == "partner":
                key = ("partner", p.partner_id.id if p.partner_id else 0)
                label = p.partner_id.display_name if p.partner_id else _("Sin contacto")
            else:
                # concept (default)
                concept = getattr(p, "prs_expense_concept_id", False)
                is_misc = getattr(p, "prs_is_misc_expense", False)
                misc = getattr(p, "prs_misc_expense_id", False)
                if is_misc or misc:
                    key = ("misc", misc.id if misc else 0)
                    label = misc.display_name if misc else _("Gastos Varios")
                elif concept:
                    key = ("concept", concept.id)
                    label = concept.display_name
                else:
                    key = ("concept", 0)
                    label = _("Sin concepto")

            groups.setdefault(key, {"label": label, "payments": []})["payments"].append(p)

        # Deterministic order
        ordered_keys = sorted(groups.keys(), key=lambda k: (k[0], k[1]))

        lines = []
        total = 0.0


        for key in ordered_keys:
            group = groups[key]

            # Stable synthetic ids (do NOT include extra '~' in the value part).
            gkey = f"{key[0]}_{key[1]}"
            gid = self._line_id("group", "", gkey)

            group_total = sum((getattr(p, "amount", 0.0) or 0.0) for p in group["payments"])
            total += group_total

            # IMPORTANT: account_reports prunes descendant lines server-side when
            # a foldable line is folded in options. That makes the caret click look
            # like it "works" (bold / caret changes) but nothing renders until a full
            # page reload. For HTML, we force foldable lines to be unfolded so the
            # full tree is sent, and we control visibility client-side.
            unfolded = True if self._prs_force_full_tree(options) else self._is_unfolded(options, gid)

            # Group header line: fold/unfolds the payments under it.
            lines.append((0, {
                "id": gid,
                "name": group["label"],
                "level": 2,
                "class": "prs_expense_line prs_group_line prs_foldable",
                "columns": [{"name": ""} for _ in range(7)],
                "unfoldable": True,
                "unfolded": unfolded,
            }))

            for p in group["payments"]:
                moves = self._get_payment_related_moves(p)
                pid = self._line_id("payment", "account.payment", p.id)
                p_unfolded = True if self._prs_force_full_tree(options) else self._is_unfolded(options, pid)

                lines.append((0, self._mk_payment_line(
                    p,
                    parent_id=gid,
                    options=options,
                    level=3,
                    unfoldable=bool(moves),
                    unfolded=p_unfolded,
                )))

                # Linked bills/invoices become linkable child lines.
                if moves:
                    for move in moves.sorted(lambda m: (getattr(m, 'invoice_date', False) or getattr(m, 'date', False) or False, m.id)):
                        lines.append((0, self._mk_move_ref_line(move, parent_id=pid, options=options, level=4)))

            # Subtotal at the bottom of the group (requested).
            lines.append((0, self._mk_group_total_line(group["label"], group_total, parent_id=gid, options=options, level=3, group_key=gkey)))
        # Grand total line
        lines.append((0, self._mk_total_line(total, options)))

        return lines
