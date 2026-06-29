# -*- coding: utf-8 -*-

import logging
import re

from odoo import api, fields, models, _
from odoo.tools.float_utils import float_compare


_logger = logging.getLogger(__name__)


_TOKEN_PATTERNS = [
    # BILL/2025/11/0018, INV/2026/0001, etc.
    re.compile(r"\b[A-Z]{2,10}/\d{4}/\d{1,2}/\d+\b"),
    re.compile(r"\b[A-Z]{2,10}/\d{4}/\d+\b"),
    # 00004-00000106 (AR invoices), 0001-00000012
    re.compile(r"\b\d{4,5}-\d{6,10}\b"),
]


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    # Solo para auditoría/debug cuando el usuario no usa auto-conciliar.
    prs_smart_suggested_aml_id = fields.Many2one(
        "account.move.line",
        string="Smart: contrapartida sugerida",
        readonly=True,
        copy=False,
    )
    prs_smart_suggested_move_id = fields.Many2one(
        "account.move",
        string="Smart: comprobante sugerido",
        readonly=True,
        copy=False,
    )
    prs_smart_suggested_note = fields.Char(
        string="Smart: nota",
        readonly=True,
        copy=False,
    )
    prs_smart_last_run = fields.Datetime(
        string="Smart: último intento",
        readonly=True,
        copy=False,
    )

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    def _prs_get_journal(self):
        self.ensure_one()
        if getattr(self, "statement_id", False) and self.statement_id:
            return self.statement_id.journal_id
        return getattr(self, "journal_id", False)

    def _prs_smart_enabled(self):
        self.ensure_one()
        journal = self._prs_get_journal()
        return bool(journal and getattr(journal, "prs_smart_reconcile_models", False))

    def _prs_smart_auto(self):
        self.ensure_one()
        journal = self._prs_get_journal()
        return bool(journal and getattr(journal, "prs_smart_reconcile_models", False) and getattr(journal, "prs_smart_reconcile_auto", False))

    def _prs_is_reconciled(self):
        self.ensure_one()
        if "is_reconciled" in self._fields:
            return bool(self.is_reconciled)
        if "move_id" in self._fields and self.move_id:
            # Si existe move y todas las líneas reconciliables están reconciliadas, lo consideramos reconciled.
            rec_lines = self.move_id.line_ids.filtered(lambda l: getattr(l.account_id, "reconcile", False))
            if rec_lines and all(getattr(l, "reconciled", False) for l in rec_lines if "reconciled" in l._fields):
                return True
        return False

    def _prs_company(self):
        self.ensure_one()
        journal = self._prs_get_journal()
        return (journal.company_id if journal else self.env.company)

    def _prs_currency(self):
        self.ensure_one()
        journal = self._prs_get_journal()
        company = self._prs_company()
        # Odoo 18: line.foreign_currency_id + amount_currency existen (según tu módulo)
        cur = False
        if "foreign_currency_id" in self._fields and self.foreign_currency_id:
            cur = self.foreign_currency_id
        if not cur and journal and journal.currency_id:
            cur = journal.currency_id
        return cur or company.currency_id

    def _prs_ref_text(self):
        self.ensure_one()
        parts = []
        for fn in ("payment_ref", "name", "ref"):
            if fn in self._fields:
                val = getattr(self, fn)
                if val:
                    parts.append(str(val))
        return " ".join(parts).strip()

    def _prs_tokens(self):
        txt = (self._prs_ref_text() or "").upper()
        tokens = []
        for pat in _TOKEN_PATTERNS:
            tokens += [m.group(0) for m in pat.finditer(txt)]
        # Dedup manteniendo orden
        seen = set()
        out = []
        for t in tokens:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    # ------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------

    def _prs_find_invoice_line_by_token(self, token, amount_abs, company, partner=None):
        """Busca un comprobante por token (name/ref/payment_reference) y devuelve un AML conciliable."""
        Move = self.env["account.move"].with_company(company.id)
        domain = [("company_id", "=", company.id)]
        # Filtrar por tipos de factura cuando exista el campo move_type
        if "move_type" in Move._fields:
            domain.append(("move_type", "in", [
                "out_invoice", "in_invoice", "out_refund", "in_refund",
                "entry",
            ]))

        fields_or = []
        if "name" in Move._fields:
            fields_or.append(("name", "=", token))
        if "ref" in Move._fields:
            fields_or.append(("ref", "=", token))
        if "payment_reference" in Move._fields:
            fields_or.append(("payment_reference", "=", token))
        if not fields_or:
            return False

        # OR chain
        dom = domain[:]
        or_dom = fields_or[0]
        for d in fields_or[1:]:
            or_dom = ["|", or_dom, d]
        dom += [or_dom]

        if partner and "partner_id" in Move._fields:
            # child_of: comercial + hijos
            dom += [("partner_id", "child_of", partner.commercial_partner_id.id)]

        moves = Move.search(dom, limit=5)
        if not moves:
            # fallback: ilike
            dom2 = domain[:]
            or_dom2 = []
            if "name" in Move._fields:
                or_dom2.append(("name", "ilike", token))
            if "ref" in Move._fields:
                or_dom2.append(("ref", "ilike", token))
            if "payment_reference" in Move._fields:
                or_dom2.append(("payment_reference", "ilike", token))
            if or_dom2:
                tmp = or_dom2[0]
                for d in or_dom2[1:]:
                    tmp = ["|", tmp, d]
                dom2 += [tmp]
                if partner and "partner_id" in Move._fields:
                    dom2 += [("partner_id", "child_of", partner.commercial_partner_id.id)]
                moves = Move.search(dom2, limit=5)

        if not moves:
            return False

        currency = self._prs_currency()
        # elegir AML por residual
        for mv in moves:
            lines = mv.line_ids
            # solo líneas reconciliables
            lines = lines.filtered(lambda l: getattr(l.account_id, "reconcile", False))
            # si existe partner, restringir
            if partner and "partner_id" in lines._fields:
                lines = lines.filtered(lambda l: l.partner_id and l.partner_id.commercial_partner_id == partner.commercial_partner_id)

            # Preferir líneas no reconciliadas y con residual = amount
            candidates = []
            for l in lines:
                if "reconciled" in l._fields and l.reconciled:
                    continue
                residual = getattr(l, "amount_residual", False)
                if residual is False:
                    continue
                if float_compare(abs(residual), amount_abs, precision_rounding=currency.rounding) == 0:
                    candidates.append(l)
            if len(candidates) == 1:
                return candidates[0]
            if len(candidates) > 1:
                # desempate: escoger la línea con mayor residual absoluto (mismo) y primera
                return candidates[0]
        return False

    def _prs_find_open_item_for_partner(self, partner, amount_abs, company):
        """Fallback: open items por partner + importe."""
        if not partner:
            return False
        AML = self.env["account.move.line"].with_company(company.id)
        currency = self._prs_currency()
        dom = [("company_id", "=", company.id)]
        if "partner_id" in AML._fields:
            dom.append(("partner_id", "child_of", partner.commercial_partner_id.id))
        if "reconciled" in AML._fields:
            dom.append(("reconciled", "=", False))
        # restringir a cuentas conciliables
        dom.append(("account_id.reconcile", "=", True))
        # traer pocos por performance
        candidates = AML.search(dom, order="date desc, id desc", limit=200)
        best = []
        for l in candidates:
            residual = getattr(l, "amount_residual", False)
            if residual is False:
                continue
            if float_compare(abs(residual), amount_abs, precision_rounding=currency.rounding) == 0:
                best.append(l)
        if len(best) == 1:
            return best[0]
        return False

    def _prs_find_payment_counterpart_aml(self, amount_abs, company, partner=None, excluded_ids=None):
        """Busca un asiento (account.move.line) que represente el pago relacionado al extracto.

        Estrategia:
        1) Intentar encontrar un account.payment posteado (monto/partner/tokens) y devolver:
           - Preferentemente la línea de liquidez (cuenta banco/caja del diario del extracto) si existe y está sin conciliar.
           - Si no, una línea conciliable de contrapartida (outstanding / receivable / payable).
        2) Si hay múltiples candidatos, aplica scoring y sólo devuelve el mejor si es claramente superior.
        """
        self.ensure_one()
        excluded_ids = excluded_ids or []
        company = company or self.company_id

        journal = self._prs_get_journal()
        bank_account = journal.default_account_id if journal else False

        # dirección del pago (inbound/outbound) según el signo del extracto
        payment_type = "inbound" if (self.amount or 0.0) > 0 else "outbound"

        # tolerancia por redondeo de moneda
        tol = (self.currency_id or company.currency_id).rounding if (self.currency_id or company.currency_id) else 0.01
        tol = max(tol, 0.01)

        # Tokens para mejorar el match (ref/label)
        tokens = self._prs_tokens()
        tokens = [t.lower() for t in tokens if t and len(t) >= 4]

        dom = [
            ("state", "=", "posted"),
            ("company_id", "=", company.id),
            ("payment_type", "=", payment_type),
            ("amount", ">=", amount_abs - tol),
            ("amount", "<=", amount_abs + tol),
        ]
        if partner:
            dom.append(("partner_id", "=", partner.id))

        payments = self.env["account.payment"].search(dom, order="date desc, id desc", limit=30)
        if not payments:
            return False

        def _text(payment):
            parts = []
            for attr in ("name", "ref", "payment_reference", "communication", "memo"):
                if hasattr(payment, attr):
                    val = getattr(payment, attr)
                    if val:
                        parts.append(str(val))
            return " ".join(parts).lower()

        def _days_delta(payment):
            if not self.date or not getattr(payment, "date", False):
                return 30
            try:
                return abs((self.date - payment.date).days)
            except Exception:
                return 30

        def _amount_close(val):
            try:
                return abs(abs(val) - amount_abs) <= tol
            except Exception:
                return False

        candidates = []
        for pay in payments:
            move = getattr(pay, "move_id", False)
            if not move:
                continue

            txt = _text(pay)
            matched_tokens = sum(1 for t in tokens if t in txt)
            token_score = min(matched_tokens, 3) / 3.0  # 0..1

            partner_score = 1.0 if (partner and pay.partner_id.id == partner.id) else (0.3 if pay.partner_id else 0.0)

            # date score: closer is better
            dd = _days_delta(pay)
            date_score = max(0.0, 1.0 - min(dd, 30) / 30.0)

            # 1) liquidity line (cuenta banco/caja)
            liquidity_line = False
            if bank_account:
                blines = move.line_ids.filtered(lambda l: l.account_id.id == bank_account.id and not l.reconciled and l.id not in excluded_ids)
                # match by amount close
                blines = blines.filtered(lambda l: _amount_close(getattr(l, "balance", 0.0)) or _amount_close(getattr(l, "amount_currency", 0.0)))
                if blines:
                    liquidity_line = blines[0]

            # 2) counterpart reconcileable line (outstanding/receivable/payable)
            counterpart_line = False
            clines = move.line_ids.filtered(lambda l: l.account_id and l.account_id.reconcile and not l.reconciled and (not bank_account or l.account_id.id != bank_account.id) and l.id not in excluded_ids)
            clines = clines.filtered(lambda l: _amount_close(getattr(l, "balance", 0.0)) or _amount_close(getattr(l, "amount_currency", 0.0)))
            if clines:
                counterpart_line = clines[0]

            # Prefer liquidity if available (1-step payments), else counterpart (2-step)
            chosen = liquidity_line or counterpart_line
            if not chosen:
                continue

            # Score ponderado
            score = 0.40 * 1.0  # amount already close by domain
            score += 0.25 * partner_score
            score += 0.25 * token_score
            score += 0.10 * date_score
            score += 0.10 * (1.0 if liquidity_line else 0.0)

            candidates.append((score, chosen))

        if not candidates:
            return False

        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_aml = candidates[0]
        second_score = candidates[1][0] if len(candidates) > 1 else 0.0

        # Reglas de seguridad: sugerir sólo si es bastante claro
        if best_score < 0.65:
            return False
        if (best_score - second_score) < 0.15 and second_score >= 0.60:
            return False

        return best_aml
    def _prs_pick_counterpart_aml(self):
        """Devuelve (aml, note) o (False, note)."""
        self.ensure_one()
        company = self._prs_company()
        amount_abs = abs(self.amount or 0.0)
        if not amount_abs:
            return False, "Sin importe"

        partner = getattr(self, "partner_id", False) or False

        # 1) Mejor caso: el extracto viene de un pago existente (2-step/3-step)
        pay_aml = self._prs_find_payment_counterpart_aml(amount_abs, company, partner)
        if pay_aml:
            return pay_aml, "Pago existente (contrapartida)"
        tokens = self._prs_tokens()
        for t in tokens:
            aml = self._prs_find_invoice_line_by_token(t, amount_abs, company, partner=partner)
            if aml:
                return aml, f"Token {t}"
            # si no había partner en la línea, igual probamos sin partner
            if not partner:
                aml = self._prs_find_invoice_line_by_token(t, amount_abs, company, partner=None)
                if aml:
                    return aml, f"Token {t} (sin partner)"

        if partner:
            aml = self._prs_find_open_item_for_partner(partner, amount_abs, company)
            if aml:
                return aml, "Open item por partner+importe"

        return False, "Sin match único"

    # ------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------

    def _prs_create_move_for_statement(self, counterpart_account, partner):
        """Crea el asiento del extracto (bank/cash vs contrapartida)."""
        self.ensure_one()
        journal = self._prs_get_journal()
        if not journal:
            raise ValueError("No journal")
        bank_account = getattr(journal, "default_account_id", False)
        if not bank_account:
            raise ValueError("Journal sin cuenta bancaria por defecto")

        amount = abs(self.amount)
        bank_debit = amount if self.amount > 0 else 0.0
        bank_credit = amount if self.amount < 0 else 0.0
        cp_debit = amount if self.amount < 0 else 0.0
        cp_credit = amount if self.amount > 0 else 0.0

        name = self.payment_ref or getattr(self, "name", False) or _("Extracto")
        Move = self.env["account.move"].with_company(journal.company_id.id)

        vals = {
            "journal_id": journal.id,
            "date": self.date,
            "ref": name,
            "line_ids": [
                (0, 0, {
                    "name": name,
                    "account_id": bank_account.id,
                    "debit": bank_debit,
                    "credit": bank_credit,
                    "partner_id": partner.id if partner else False,
                }),
                (0, 0, {
                    "name": name,
                    "account_id": counterpart_account.id,
                    "debit": cp_debit,
                    "credit": cp_credit,
                    "partner_id": partner.id if partner else False,
                }),
            ],
        }
        move = Move.create(vals)
        if hasattr(move, "action_post"):
            move.action_post()
        elif hasattr(move, "post"):
            move.post()
        return move

    def _prs_apply_auto_reconcile(self, aml):
        """Crea asiento y reconcilia contra el AML existente."""
        self.ensure_one()
        if self._prs_is_reconciled():
            return False
        # evitar duplicar
        if "move_id" in self._fields and self.move_id:
            return False

        partner = aml.partner_id or getattr(aml.move_id, "partner_id", False)
        if partner:
            partner = partner.commercial_partner_id

        move = self._prs_create_move_for_statement(aml.account_id, partner)
        # link al statement line si existe
        ctx = dict(self.env.context or {})
        ctx["prs_skip_smart_reconcile"] = True
        if "move_id" in self._fields:
            self.with_context(**ctx).write({"move_id": move.id})
        if "partner_id" in self._fields and partner and not self.partner_id:
            self.with_context(**ctx).write({"partner_id": partner.id})
        if "to_check" in self._fields:
            self.with_context(**ctx).write({"to_check": False})

        # encontrar línea contrapartida creada para reconciliar
        created = move.line_ids.filtered(lambda l: l.account_id == aml.account_id and (not partner or l.partner_id.commercial_partner_id == partner))
        if created:
            try:
                (created[0] + aml).reconcile()
            except Exception:
                _logger.exception("Smart reconcile: no se pudo reconciliar statement line %s con aml %s", self.id, aml.id)
                return False
        return True

    # ------------------------------------------------------------
    # Entrypoints
    # ------------------------------------------------------------

    def _prs_smart_reconcile_run_batch(self):
        """Intenta sugerir / autoconciliar para las líneas del recordset."""
        for line in self:
            if not line._prs_smart_enabled():
                continue
            if (line.env.context or {}).get("prs_skip_smart_reconcile"):
                continue
            if line._prs_is_reconciled():
                continue

            aml, note = line._prs_pick_counterpart_aml()
            vals = {
                "prs_smart_last_run": fields.Datetime.now(),
                "prs_smart_suggested_note": note,
                "prs_smart_suggested_aml_id": aml.id if aml else False,
                "prs_smart_suggested_move_id": aml.move_id.id if aml else False,
            }
            try:
                line.with_context(prs_skip_smart_reconcile=True).write(vals)
            except Exception:
                # no rompemos
                pass

            if aml and line._prs_smart_auto():
                try:
                    line._prs_apply_auto_reconcile(aml)
                except Exception:
                    _logger.exception("Smart reconcile: fallo auto en statement line %s", line.id)
        return True

    @api.model
    def _prs_smart_reconcile_run_journal(self, journal):
        """Corre smart en pendientes del diario (llamado al abrir conciliación)."""
        if not journal or journal.type not in ("cash", "bank"):
            return False
        if not getattr(journal, "prs_smart_reconcile_models", False):
            return False
        Line = self.env["account.bank.statement.line"].with_company(journal.company_id.id)
        dom = [("journal_id", "=", journal.id)]
        if "is_reconciled" in Line._fields:
            dom.append(("is_reconciled", "=", False))
        # solo estados abiertos si existe el campo
        if "statement_id" in Line._fields and "prs_state" in self.env["account.bank.statement"]._fields:
            dom += [("statement_id.prs_state", "=", "open")]
        lines = Line.search(dom, order="date desc, id desc", limit=300)
        if lines:
            lines._prs_smart_reconcile_run_batch()
        return True
