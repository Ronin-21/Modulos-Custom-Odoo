# -*- coding: utf-8 -*-
import logging
import re

from odoo import api, models

_logger = logging.getLogger(__name__)


class AccountBankStatementLineSmart(models.Model):
    _inherit = 'account.bank.statement.line'

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    def _prs_smart_reconcile_enabled(self):
        """Return True if Smart reconciliation is enabled for the line journal."""
        self.ensure_one()
        journal = False
        if 'journal_id' in self._fields and self.journal_id:
            journal = self.journal_id
        elif 'statement_id' in self._fields and self.statement_id and self.statement_id.journal_id:
            journal = self.statement_id.journal_id
        return bool(journal and getattr(journal, 'prs_smart_reconcile_models', False))

    def _prs_smart_is_reconciled(self):
        """Best-effort check to avoid re-processing."""
        self.ensure_one()
        for f in ('is_reconciled',):
            if f in self._fields:
                try:
                    return bool(getattr(self, f))
                except Exception:
                    pass
        return False

    def _prs_smart_company(self):
        self.ensure_one()
        if 'company_id' in self._fields and self.company_id:
            return self.company_id
        journal = False
        if 'journal_id' in self._fields and self.journal_id:
            journal = self.journal_id
        elif 'statement_id' in self._fields and self.statement_id:
            journal = self.statement_id.journal_id
        return journal.company_id if journal else self.env.company

    def _prs_smart_currency(self):
        self.ensure_one()
        # Statement lines are usually in company currency; keep tolerance based on company currency.
        company = self._prs_smart_company()
        return company.currency_id

    def _prs_smart_tol(self):
        cur = self._prs_smart_currency()
        try:
            return float(cur.rounding or 0.01) * 2.0
        except Exception:
            return 0.02

    def _prs_account_is_receivable_or_payable(self, account):
        if not account:
            return False
        # Newer: account_type
        if 'account_type' in account._fields:
            return account.account_type in ('asset_receivable', 'liability_payable', 'receivable', 'payable')
        # Older: internal_type
        if 'internal_type' in account._fields:
            return account.internal_type in ('receivable', 'payable')
        # Very old: user_type_id.type
        if 'user_type_id' in account._fields and account.user_type_id and 'type' in account.user_type_id._fields:
            return account.user_type_id.type in ('receivable', 'payable')
        return False

    def _prs_get_ref_text(self):
        self.ensure_one()
        parts = []
        for f in ('payment_ref', 'name', 'ref', 'communication', 'narration'):
            if f in self._fields:
                val = getattr(self, f) or ''
                if val:
                    parts.append(str(val))
        return ' '.join(parts).strip()

    def _prs_partner_for_matching(self):
        self.ensure_one()
        partner = False
        if 'partner_id' in self._fields and self.partner_id:
            partner = self.partner_id
        # If no partner, we don't force it from payment_id: payment_id lines are skipped by design.
        return partner.commercial_partner_id if partner else False

    def _prs_open_items_for_partner(self, partner, amount_abs, company):
        """Return move lines (receivable/payable) with residual matching the statement amount."""
        Aml = self.env['account.move.line']
        dom = [('company_id', '=', company.id), ('partner_id', 'child_of', partner.id)]
        if 'parent_state' in Aml._fields:
            dom.append(('parent_state', '=', 'posted'))
        else:
            dom.append(('move_id.state', '=', 'posted'))

        # Unreconciled filter
        if 'reconciled' in Aml._fields:
            dom.append(('reconciled', '=', False))
        elif 'full_reconcile_id' in Aml._fields:
            dom.append(('full_reconcile_id', '=', False))

        # Avoid blocked lines (best effort)
        if 'blocked' in Aml._fields:
            dom.append(('blocked', '=', False))

        # Only potential open items; we'll filter account type in python
        candidates = Aml.search(dom, limit=200, order='date desc, id desc')
        tol = self._prs_smart_tol()
        res = []
        for aml in candidates:
            try:
                if not self._prs_account_is_receivable_or_payable(aml.account_id):
                    continue
                residual = getattr(aml, 'amount_residual', 0.0)
                if abs(abs(residual) - amount_abs) <= tol:
                    res.append(aml)
            except Exception:
                continue
        return res
def _prs_find_invoice_aml_by_ref(self, ref_text, amount_abs, company, partner=False):
    """Try to find an invoice/bill open item line using reference text.

    Soporta referencias típicas:
    - INV/2026/0001
    - BILL/2025/11/0018  (4 segmentos)
    - 0001-00000012
    - FA-A 00004-00000106 / 00004-00000106 (AR)
    """
    if not ref_text:
        return False

    tokens = set()

    patterns = [
        r"\b[A-Z]{2,6}/\d{4}/\d{2}/\d+\b",    # BILL/2025/11/0018
        r"\b[A-Z]{2,6}/\d{4}/\d+\b",          # INV/2026/0001
        r"\b\d{4}-\d{8}\b",                    # 0001-00000012
        r"\b\d{5}-\d{8}\b",                    # 00004-00000106
        r"\b[A-Z]{2}-[A-Z]\s+\d{5}-\d{8}\b",  # FA-A 00004-00000106
    ]
    for pat in patterns:
        for mm in re.finditer(pat, ref_text or ""):
            tokens.add(mm.group(0).strip())

    # Limpieza: para FA-A 00004-00000106 también guardamos 00004-00000106
    cleaned = set()
    for t in tokens:
        cleaned.add(t)
        m = re.search(r"(\d{5}-\d{8})", t)
        if m:
            cleaned.add(m.group(1))
    tokens = cleaned

    # También considerar un token alfanumérico largo (muy conservador)
    if not tokens:
        m = re.search(r"\b[A-Z]{2,6}\d{4,}\b", ref_text or "")
        if m:
            tokens.add(m.group(0))

    if not tokens:
        return False

    Move = self.env['account.move']
    tol = self._prs_smart_tol()

    # Buscar movimientos por token (name / ref / payment_reference)
    candidate_moves = self.env['account.move']
    for token in list(tokens)[:8]:
        dom = [('company_id', '=', company.id)]

        if 'state' in Move._fields:
            dom.append(('state', '=', 'posted'))

        or_dom = []
        if 'name' in Move._fields:
            or_dom.append(('name', '=', token))
        if 'ref' in Move._fields:
            or_dom.append(('ref', '=', token))
        if 'payment_reference' in Move._fields:
            or_dom.append(('payment_reference', '=', token))
        if not or_dom:
            continue

        d = dom[:]
        if len(or_dom) == 1:
            d.append(or_dom[0])
        else:
            ors = []
            for i, clause in enumerate(or_dom):
                if i:
                    ors = ['|'] + ors
                ors += [clause]
            d += ors

        candidate_moves |= Move.search(d, limit=5)

    if not candidate_moves:
        return False

    # Filtrar por partner comercial si está disponible
    if partner:
        pid = partner.id
        candidate_moves = candidate_moves.filtered(lambda m: m.partner_id and m.partner_id.commercial_partner_id.id == pid)

    amls = self.env['account.move.line']
    for mv in candidate_moves:
        for aml in mv.line_ids:
            try:
                if not self._prs_account_is_receivable_or_payable(aml.account_id):
                    continue
                if getattr(aml, 'reconciled', False):
                    continue
                residual = getattr(aml, 'amount_residual', 0.0)
                if abs(abs(residual) - amount_abs) <= tol:
                    amls |= aml
            except Exception:
                continue

    if not amls:
        return False

    if len(amls) == 1:
        return amls[0]

    exact_names = set(tokens)
    exact = amls.filtered(lambda l: l.move_id and getattr(l.move_id, 'name', '') in exact_names)
    if len(exact) == 1:
        return exact[0]

    return False
def _prs_pick_counterpart_open_item(self):
    """Return a single matching open item AML or False (to avoid wrong auto-matches).

    Estrategia:
    1) Si hay un match único por importe (open item receivable/payable) lo usamos.
    2) Si hay 0 o múltiples matches, intentamos desambiguar por referencia (payment_ref/name/ref).
    """
    self.ensure_one()

    # Safety: don't touch lines created from already posted payments (avoid double entries)
    if 'payment_id' in self._fields and self.payment_id:
        return False

    partner = self._prs_partner_for_matching()
    company = self._prs_smart_company()
    amount_abs = abs(self.amount or 0.0)
    if not amount_abs:
        return False

    ref_text = self._prs_get_ref_text()

    if partner:
        matches = self._prs_open_items_for_partner(partner, amount_abs, company)
        if len(matches) == 1:
            return matches[0]
        # Si hay varios, probamos por referencia para quedarnos con uno.
        if len(matches) > 1:
            aml = self._prs_find_invoice_aml_by_ref(ref_text, amount_abs, company, partner=partner)
            return aml or False

    # Sin partner o sin match por importe: intentamos por referencia.
    aml = self._prs_find_invoice_aml_by_ref(ref_text, amount_abs, company, partner=partner)
    return aml or False

    def _prs_process_reconciliation_new_line(self, account_id, partner_id=False):
        """Create reconciliation move line (counterpart) through process_reconciliation."""
        self.ensure_one()
        if not hasattr(self, 'process_reconciliation'):
            return False

        amt = abs(self.amount or 0.0)
        if not amt:
            return False

        debit = amt if (self.amount or 0.0) < 0 else 0.0
        credit = amt if (self.amount or 0.0) > 0 else 0.0

        label = self._prs_get_ref_text() or 'Smart Reconcile'
        new_aml_dicts = [{
            'name': label,
            'account_id': account_id,
            'partner_id': partner_id or False,
            'debit': debit,
            'credit': credit,
        }]

        empty_aml = self.env['account.move.line']
        self.with_context(prs_skip_smart_reconcile=True, default_to_check=False).process_reconciliation(
            [], empty_aml, new_aml_dicts
        )
        return True

    def _prs_get_last_reconcile_move(self):
        self.ensure_one()
        # Common field names across versions
        for f in ('move_id', 'journal_entry_id'):
            if f in self._fields and getattr(self, f):
                return getattr(self, f)
        if 'journal_entry_ids' in self._fields and self.journal_entry_ids:
            return self.journal_entry_ids[-1]
        if 'move_ids' in self._fields and self.move_ids:
            return self.move_ids[-1]
        return False

    def _prs_find_created_counterpart_line(self, account, partner, amount_abs):
        self.ensure_one()
        move = self._prs_get_last_reconcile_move()
        if not move:
            return False
        tol = self._prs_smart_tol()
        partner_id = partner.id if partner else False
        for ml in move.line_ids:
            try:
                if ml.account_id.id != account.id:
                    continue
                if partner_id and ml.partner_id and ml.partner_id.commercial_partner_id.id != partner_id:
                    continue
                if getattr(ml, 'reconciled', False):
                    continue
                if abs(abs(ml.balance) - amount_abs) <= tol:
                    return ml
            except Exception:
                continue
        return False

    # ---------------------------------------------------------------------
    # Main runner
    # ---------------------------------------------------------------------

    def _prs_smart_reconcile_run_batch(self):
        """Try to smart-reconcile each line (best effort, never raises)."""
        for line in self:
            try:
                if line.env.context.get('prs_skip_smart_reconcile'):
                    continue
                if not line._prs_smart_reconcile_enabled():
                    continue
                if line._prs_smart_is_reconciled():
                    continue
                if not (line.amount or 0.0):
                    continue

                # 1) Try exact open item match (invoice/bill).
                aml = line._prs_pick_counterpart_open_item()
                if aml:
                    amount_abs = abs(line.amount or 0.0)
                    partner = aml.partner_id.commercial_partner_id if aml.partner_id else False
                    # Create counterpart on receivable/payable account then reconcile with exact AML
                    ok = line._prs_process_reconciliation_new_line(
                        account_id=aml.account_id.id,
                        partner_id=partner.id if partner else False,
                    )
                    if ok:
                        # Reconcile created line with the chosen open item
                        created = line._prs_find_created_counterpart_line(aml.account_id, partner, amount_abs)
                        if created:
                            (created + aml).with_context(prs_skip_smart_reconcile=True).reconcile()
                    continue

                # 2) If no open item match, but it's a pure partner payment with no open items,
                #    post it against the partner receivable/payable account.
                partner = line._prs_partner_for_matching()
                if not partner:
                    continue

                company = line._prs_smart_company()
                amount_abs = abs(line.amount or 0.0)

                # If partner has any open items, do not guess (leave to manual).
                # The helper filters by amount, so we need a separate lightweight check for any open items:
                Aml = line.env['account.move.line']
                dom = [('company_id', '=', company.id), ('partner_id', 'child_of', partner.id)]
                if 'parent_state' in Aml._fields:
                    dom.append(('parent_state', '=', 'posted'))
                else:
                    dom.append(('move_id.state', '=', 'posted'))
                if 'reconciled' in Aml._fields:
                    dom.append(('reconciled', '=', False))
                elif 'full_reconcile_id' in Aml._fields:
                    dom.append(('full_reconcile_id', '=', False))
                candidates = Aml.search(dom, limit=50)
                has_open_items = any(line._prs_account_is_receivable_or_payable(a.account_id) and abs(getattr(a, 'amount_residual', 0.0)) > line._prs_smart_tol() for a in candidates)

                if has_open_items:
                    continue

                # Choose receivable/payable depending on sign
                partner_c = partner.with_company(company)
                account = False
                if (line.amount or 0.0) > 0:
                    account = getattr(partner_c, 'property_account_receivable_id', False)
                else:
                    account = getattr(partner_c, 'property_account_payable_id', False)

                if not account:
                    continue

                line._prs_process_reconciliation_new_line(
                    account_id=account.id,
                    partner_id=partner.id,
                )

            except Exception:
                _logger.exception("Smart reconcile: error procesando statement line %s", line.id)
        return True
