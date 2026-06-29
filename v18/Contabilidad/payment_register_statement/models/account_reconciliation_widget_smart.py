# -*- coding: utf-8 -*-
from odoo import api, models


class AccountReconciliationWidget(models.AbstractModel):
    _inherit = "account.reconciliation.widget"

    @api.model
    def get_bank_statement_line_data(self, st_line_ids, excluded_ids=None, *args, **kwargs):
        """Preselecciona automáticamente el asiento de contrapartida cuando
        el diario tiene activado 'Modelos de Conciliación Smart'.

        - Mantiene el comportamiento estándar de Odoo.
        - Si encontramos un match 'fuerte' (token o pago existente), reemplazamos
          la reconciliation_proposition para que el widget lo seleccione (y no quede 'Nuevo').
        """
        excluded_ids = excluded_ids or []
        res = super().get_bank_statement_line_data(st_line_ids, excluded_ids, *args, **kwargs)
        try:
            lines_payload = res.get("lines") or []
        except Exception:
            return res

        if not lines_payload:
            return res

        StLine = self.env["account.bank.statement.line"]

        # Armamos un dict id -> record para evitar browse repetidos
        st_ids = []
        for lp in lines_payload:
            st = lp.get("st_line") or {}
            st_id = st.get("id") or lp.get("st_line_id")
            if st_id:
                st_ids.append(st_id)

        st_map = {l.id: l for l in StLine.browse(st_ids).exists()}

        for lp in lines_payload:
            st = lp.get("st_line") or {}
            st_id = st.get("id") or lp.get("st_line_id")
            st_line = st_map.get(st_id)
            if not st_line:
                continue

            journal = st_line.journal_id
            if not (journal and getattr(journal, "prs_smart_reconcile_models", False)):
                continue

            # Elegimos el mejor AML sugerido por nuestra lógica
            aml = getattr(st_line, "prs_smart_suggested_aml_id", False)
            note = getattr(st_line, "prs_smart_suggested_note", "") or ""
            if not aml:
                try:
                    aml, note = st_line._prs_pick_counterpart_aml(excluded_ids=excluded_ids, company=st_line.company_id)
                except Exception:
                    continue

            if not aml or aml.id in set(excluded_ids):
                continue

            # Solo preseleccionamos cuando el match es confiable
            if not (note.startswith("Token") or note.startswith("Pago existente")):
                continue

            target_currency = st_line.currency_id or journal.currency_id or st_line.company_id.currency_id

            prepared = None
            # Intentamos usar el helper estándar del widget para preparar AMLs
            try:
                prepared = self._prepare_move_lines(aml, target_currency=target_currency, target_date=st_line.date)
            except TypeError:
                try:
                    prepared = self._prepare_move_lines(aml, target_currency=target_currency)
                except Exception:
                    prepared = None
            except Exception:
                prepared = None

            if prepared is None:
                continue

            lp["reconciliation_proposition"] = prepared
            # si existe model_id, lo limpiamos para no forzar modelos genéricos
            if "model_id" in lp:
                lp["model_id"] = False

        return res
