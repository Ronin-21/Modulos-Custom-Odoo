# -*- coding: utf-8 -*-
"""
Utilidades compartidas del módulo payment_register_statement.

Centraliza funciones helpers que antes estaban duplicadas en múltiples
archivos del módulo.
"""


def prs_is_pos(env):
    """Detecta si la acción en curso proviene del POS."""
    ctx = env.context or {}
    return bool(
        ctx.get("pos_session_id")
        or ctx.get("from_pos")
        or ctx.get("pos_config_id")
        or ctx.get("active_model") in ("pos.session", "pos.order", "pos.payment")
    )


def prs_vals_look_like_pos(vals):
    """Heurística por texto: detecta pagos/extractos del POS cuando no viene contexto explícito."""
    if not isinstance(vals, dict):
        return False
    parts = []
    for k in ("memo", "ref", "payment_reference", "communication", "name", "payment_ref"):
        v = vals.get(k)
        if v:
            parts.append(str(v))
    t = " ".join(parts).lower()
    return (
        "pos/" in t
        or "punto de venta" in t
        or "pos session" in t
        or "pos.session" in t
    )


def prs_journal_uses_receivable(journal):
    """Detecta si el diario usa una cuenta de tipo Por cobrar (asset_receivable).

    Revisa en este orden:
    1. La cuenta por defecto del diario (default_account_id).
    2. Las cuentas de los métodos de pago de entrada (inbound_payment_method_line_ids).
    3. Los métodos de pago POS que usan este diario (cubre Tarjetas de Crédito).
    """
    if not journal:
        return False

    # 1) Cuenta por defecto del diario
    default_acct = getattr(journal, 'default_account_id', False)
    if default_acct and getattr(default_acct, 'account_type', '') == 'asset_receivable':
        return True

    # 2) Cuentas de métodos de pago contables del diario
    for ml in getattr(journal, 'inbound_payment_method_line_ids', []):
        acct = getattr(ml, 'payment_account_id', False)
        if acct and getattr(acct, 'account_type', '') == 'asset_receivable':
            return True

    # 3) Métodos de pago POS que apuntan a este diario
    env = journal.env
    if 'pos.payment.method' in env:
        try:
            pos_methods = env['pos.payment.method'].search(
                [('journal_id', '=', journal.id)], limit=20
            )
            for pm in pos_methods:
                for fname in ('receivable_account_id', 'outstanding_account_id', 'account_id'):
                    acct = getattr(pm, fname, False)
                    if acct and getattr(acct, 'account_type', '') == 'asset_receivable':
                        return True
        except Exception:
            pass

    return False
