# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ReportPrsExpensesPdf(models.AbstractModel):
    _name = "report.payment_register_statement_v19.report_prs_expenses_pdf"
    _description = "Reporte PDF - Gastos / Compras"

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env["prs.expense.report.wizard"].browse(docids).exists()
        wizard = wizard[:1]  # por si vinieran varios
        payments = wizard._get_payments() if wizard else self.env["account.payment"]

        def provider_label(p):
            ref = (p.partner_id.ref or "").strip()
            name = (p.partner_id.name or "").strip()
            return f"{ref} {name}".strip() if ref else name

        def detail_label(p):
            invs = getattr(p, "reconciled_invoice_ids", self.env["account.move"])
            invs = invs.filtered(lambda m: m and m.move_type in ("in_invoice", "in_refund", "in_receipt")) if invs else invs
            if invs:
                if len(invs) == 1:
                    return (invs[0].name or invs[0].ref or invs[0].payment_reference or "").strip()
                return ", ".join([(m.name or m.ref or m.payment_reference or "").strip() for m in invs if (m.name or m.ref or m.payment_reference)])
            # fallback: memo/ref
            for f in ("memo", "ref", "payment_reference", "name"):
                if f in p._fields and getattr(p, f):
                    return str(getattr(p, f)).strip()
            return ""

        def payment_amount(p):
            # mostramos siempre positivo
            try:
                return abs(p.amount)
            except Exception:
                return 0.0

        def concept_of(p):
            concept = getattr(p, "prs_expense_concept_id", False)
            if concept:
                return concept
            invs = getattr(p, "reconciled_invoice_ids", False)
            if invs:
                c = invs[:1].prs_expense_concept_id
                if c:
                    return c
            partner = p.partner_id
            if partner and "prs_expense_concept_id" in partner._fields and partner.prs_expense_concept_id:
                return partner.prs_expense_concept_id
            return False

        def root_concept(concept):
            r = concept
            while r and r.parent_id:
                r = r.parent_id
            return r

        def title_for(concept):
            return f"{concept.id} {concept.name}".strip()

        # Build lines
        lines = []
        for p in payments:
            lines.append({
                "date": p.date,
                "date_str": p.date.strftime("%d/%m/%Y") if p.date else "",
                "provider": provider_label(p),
                "detail": detail_label(p),
                "amount": payment_amount(p),
                "payment_id": p.id,
            })

        # Grouping
        report_data = {
            "mode": wizard.group_mode if wizard else "concept",
            "total": sum([l["amount"] for l in lines]) if lines else 0.0,
            "currency": (wizard.currency_id if wizard else self.env.company.currency_id),
            "date_from": wizard.date_from if wizard else (min([l["date"] for l in lines if l["date"]]) if lines else False),
            "date_to": wizard.date_to if wizard else (max([l["date"] for l in lines if l["date"]]) if lines else False),
            "single_root": False,
            "groups": [],
            "lines": [],
        }

        if report_data["mode"] == "date":
            report_data["lines"] = lines
        else:
            # root -> {title, lines, subs{title: {title, lines, total}}, total}
            roots = {}
            for p, l in zip(payments, lines):
                concept = concept_of(p)
                if concept:
                    r = root_concept(concept)
                    root_key = r.id
                    root_title = title_for(r)
                    sub = concept if concept.parent_id else False
                else:
                    if getattr(p, "prs_is_misc_expense", False):
                        root_key = "misc"
                        root_title = "Gastos Varios"
                    else:
                        root_key = "none"
                        root_title = "Sin concepto"
                    sub = False

                root = roots.setdefault(root_key, {"title": root_title, "lines": [], "subs": {}, "total": 0.0})
                if sub:
                    sub_key = sub.id
                    sg = root["subs"].setdefault(sub_key, {"title": title_for(sub), "lines": [], "total": 0.0})
                    sg["lines"].append(l)
                    sg["total"] += l["amount"]
                else:
                    root["lines"].append(l)
                root["total"] += l["amount"]

            # sort roots by title
            def root_sort_key(item):
                k, v = item
                # numeric roots first
                if isinstance(k, int):
                    return (0, v["title"])
                return (1, v["title"])
            groups = []
            for k, v in sorted(roots.items(), key=root_sort_key):
                # sort lines inside groups
                v["lines"] = sorted(v["lines"], key=lambda x: (x["date"] or fields.Date.today(), x["payment_id"]), reverse=(wizard.order == "desc" if wizard else False))
                subs_list = []
                for sk, sv in sorted(v["subs"].items(), key=lambda kv: kv[1]["title"]):
                    sv["lines"] = sorted(sv["lines"], key=lambda x: (x["date"] or fields.Date.today(), x["payment_id"]), reverse=(wizard.order == "desc" if wizard else False))
                    subs_list.append(sv)
                v["subs"] = subs_list
                groups.append(v)

            report_data["groups"] = groups
            if len(groups) == 1:
                report_data["single_root"] = groups[0]["title"]

        return {
            "doc_ids": docids,
            "doc_model": "prs.expense.report.wizard",
            "docs": wizard,
            "report_data": report_data,
        }
