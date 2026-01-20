# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.tools.misc import formatLang


class ReportSaleDetails(models.AbstractModel):
    _inherit = "report.point_of_sale.report_saledetails"

    def _ppc_to_text(self, value):
        if not value:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            lang = self.env.context.get("lang") or self.env.user.lang or ""
            if lang and value.get(lang):
                return value[lang]
            if lang and "_" in lang:
                short = lang.split("_")[0]
                if value.get(short):
                    return value[short]
            for k in ("es_AR", "es", "en_US", "en"):
                if value.get(k):
                    return value[k]
            for v in value.values():
                if v:
                    return v
            return ""
        return str(value)

    @api.model
    def _get_report_values(self, docids, data=None):
        res = super()._get_report_values(docids, data=data)

        session_ids = self._ppc_get_session_ids(docids, data, res)
        sessions = self.env["pos.session"].browse(session_ids).exists()

        def fmt(amount, currency):
            return (formatLang(self.env, amount or 0.0, currency_obj=currency) or "").replace("\xa0", " ")

        def safe_sum(recs, field_name):
            if not recs:
                return 0.0
            if field_name not in recs._fields:
                return 0.0
            return sum(recs.mapped(field_name)) or 0.0

        card_sessions = []
        for s in sessions:
            currency = s.currency_id or s.company_id.currency_id

            # Obtener TODOS los pagos (totales por método)
            all_payments = s.get_all_payment_totals() or []
            
            # Obtener solo pagos con tarjeta (desglose)
            card_payments = s.get_card_payment_totals() or []
            
            # ✅ NUEVO: Obtener pagos sin tarjeta
            non_card_payments = s.get_non_card_payment_details() or []

            # Construir grupos COMBINADOS
            groups_map = {}
            total_amount = 0.0
            total_trans = 0

            # 1) Agregar TODOS los métodos con sus totales correctos
            for payment in all_payments:
                method_id = payment['payment_method_id']
                method_name = self._ppc_to_text(payment.get("payment_method_name")) or "Sin método"
                
                groups_map[method_id] = {
                    "payment_method_id": method_id,
                    "payment_method_name": method_name,
                    "lines": [],  # Líneas CON tarjeta
                    "non_card_lines": [],  # ✅ NUEVO: Líneas SIN tarjeta
                    "total_amount": float(payment.get("total_amount") or 0.0),
                    "total_amount_fmt": fmt(float(payment.get("total_amount") or 0.0), currency),
                    "total_trans": int(payment.get("transaction_count") or 0),
                    "has_card_details": int(payment.get("has_card_details") or 0) > 0,
                }
                
                total_amount += float(payment.get("total_amount") or 0.0)
                total_trans += int(payment.get("transaction_count") or 0)

            # 2) Agregar desglose de tarjetas
            for card_row in card_payments:
                method_id = card_row['payment_method_id']
                
                if method_id in groups_map:
                    line = {
                        "card_name": self._ppc_to_text(card_row.get("card_name")) or "",
                        "installment_plan_name": self._ppc_to_text(card_row.get("installment_plan_name")) or "",
                        "installments": int(card_row.get("installments") or 1),
                        "installment_percent": float(card_row.get("installment_percent") or 0),
                        "transaction_count": int(card_row.get("transaction_count") or 0),
                        "total_amount": float(card_row.get("total_amount") or 0),
                        "total_amount_fmt": fmt(float(card_row.get("total_amount") or 0), currency),
                        "coupons": card_row.get("coupons") or "",
                    }
                    
                    groups_map[method_id]["lines"].append(line)

            # ✅ 3) MEJORADO: Agregar desglose de pagos SIN tarjeta (ya agrupados)
            for non_card_row in non_card_payments:
                method_id = non_card_row['payment_method_id']
                
                if method_id in groups_map:
                    # Determinar si son mayormente pagos mixtos o directos
                    total_count = int(non_card_row.get("transaction_count") or 0)
                    mixed_count = int(non_card_row.get("mixed_count") or 0)
                    is_mostly_mixed = mixed_count > (total_count / 2)
                    
                    line = {
                        "payment_type": "Pagos mixtos" if is_mostly_mixed else "Pagos directos",
                        "transaction_count": total_count,
                        "total_amount": float(non_card_row.get("total_amount") or 0),
                        "total_amount_fmt": fmt(float(non_card_row.get("total_amount") or 0), currency),
                        "mixed_count": mixed_count,
                        "direct_count": total_count - mixed_count,
                        # Opcional: referencias de órdenes para debug
                        "order_references": non_card_row.get("order_references") or "",
                    }
                    
                    # Solo agregar UNA línea por método (agrupada)
                    groups_map[method_id]["non_card_lines"].append(line)

            # Calcular subtotales
            for method_id, group in groups_map.items():
                if group["has_card_details"] and group["lines"]:
                    # Total de líneas con tarjeta
                    card_total = sum([float(l.get("total_amount") or 0) for l in group["lines"]])
                    card_trans = sum([int(l.get("transaction_count") or 0) for l in group["lines"]])
                    
                    group["card_subtotal"] = card_total
                    group["card_subtotal_fmt"] = fmt(card_total, currency)
                    group["card_trans"] = card_trans
                
                # ✅ Total de líneas SIN tarjeta
                if group["non_card_lines"]:
                    non_card_total = sum([float(l.get("total_amount") or 0) for l in group["non_card_lines"]])
                    non_card_trans = sum([int(l.get("transaction_count") or 0) for l in group["non_card_lines"]])
                    
                    group["non_card_total"] = non_card_total
                    group["non_card_total_fmt"] = fmt(non_card_total, currency)
                    group["non_card_trans"] = non_card_trans
                    group["has_non_card"] = non_card_total > 0.01

            # Split fiscal/no fiscal (sin cambios)
            orders = s.order_ids.filtered(lambda o: o.state in ("paid", "done", "invoiced"))

            def is_fiscal(o):
                return bool(getattr(o, "account_move_id", False) or getattr(o, "account_move", False))

            fiscal_orders = orders.filtered(is_fiscal)
            non_fiscal_orders = orders - fiscal_orders

            nf_total = safe_sum(non_fiscal_orders, "amount_total")
            nf_tax = safe_sum(non_fiscal_orders, "amount_tax")
            nf_untaxed = nf_total - nf_tax

            f_total = safe_sum(fiscal_orders, "amount_total")
            f_tax = safe_sum(fiscal_orders, "amount_tax")
            f_untaxed = f_total - f_tax

            journal_split = {
                "non_fiscal": {
                    "journal_name": (s.config_id.journal_id.display_name if s.config_id.journal_id else "Punto de Venta"),
                    "count": len(non_fiscal_orders),
                    "amount_untaxed": nf_untaxed,
                    "amount_tax": nf_tax,
                    "amount_total": nf_total,
                    "amount_untaxed_fmt": fmt(nf_untaxed, currency),
                    "amount_tax_fmt": fmt(nf_tax, currency),
                    "amount_total_fmt": fmt(nf_total, currency),
                },
                "fiscal": {
                    "journal_name": (
                        (getattr(s.config_id, "invoice_journal_id", False) and s.config_id.invoice_journal_id.display_name)
                        or "Factura Electrónica POS"
                    ),
                    "count": len(fiscal_orders),
                    "amount_untaxed": f_untaxed,
                    "amount_tax": f_tax,
                    "amount_total": f_total,
                    "amount_untaxed_fmt": fmt(f_untaxed, currency),
                    "amount_tax_fmt": fmt(f_tax, currency),
                    "total_fmt": fmt(f_total, currency),
                },
            }

            groups_list = sorted(groups_map.values(), key=lambda x: (x.get("payment_method_name") or "").lower())

            card_sessions.append({
                "session_id": s.id,
                "session_name": s.name,
                "currency_id": currency.id,
                "groups": groups_list,
                "total_amount": total_amount,
                "total_amount_fmt": fmt(total_amount, currency),
                "total_trans": total_trans,
                "journal_split": journal_split,
            })

        res["pos_payment_custom_card_sessions"] = card_sessions
        return res

    @api.model
    def _ppc_get_session_ids(self, docids, data, res):
        def _norm(val):
            if not val:
                return []
            if isinstance(val, int):
                return [val]
            if isinstance(val, (list, tuple, set)):
                out = []
                for v in val:
                    if isinstance(v, int):
                        out.append(v)
                    elif isinstance(v, (list, tuple)) and v and isinstance(v[0], int):
                        out.append(v[0])
                return out
            return []

        data = dict(data or {})

        for k in ("session_ids", "pos_session_ids", "session_id", "pos_session_id"):
            ids = _norm(data.get(k))
            if ids:
                return ids

        form = data.get("form") or {}
        for k in ("session_ids", "pos_session_ids", "session_id", "pos_session_id"):
            ids = _norm(form.get(k))
            if ids:
                return ids

        res_data = (res or {}).get("data") or {}
        for k in ("session_ids", "pos_session_ids", "session_id", "pos_session_id"):
            ids = _norm(res_data.get(k))
            if ids:
                return ids

        if docids and self.env["pos.session"].browse(docids).exists():
            return self.env["pos.session"].browse(docids).exists().ids

        return []