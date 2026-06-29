# -*- coding: utf-8 -*-
"""
PRS — Reparación de líneas huérfanas (account.bank.statement.line sin statement_id)

Ejecutar desde la shell de Odoo:
    odoo shell -d <base> < prs_repair_orphan_lines.py

O como script manual:
    env.cr.execute("...")  / env['account.bank.statement.line'].search(...)

El script busca todas las líneas sin estado de cuenta en diarios con
auto_extract_enabled y las asigna al estado ABIERTO más adecuado por fecha.
Al final recalcula los saldos en cadena de todos los estados afectados.
"""
import logging
from odoo import fields

_logger = logging.getLogger(__name__)


def repair_orphan_lines(env):
    StatementLine = env['account.bank.statement.line']
    Statement = env['account.bank.statement']

    # 1. Buscar todas las líneas huérfanas en diarios con auto_extract_enabled
    orphans = StatementLine.search([
        ('statement_id', '=', False),
        ('journal_id.auto_extract_enabled', '=', True),
    ], order='journal_id asc, date asc, id asc')

    if not orphans:
        _logger.info("PRS repair: no se encontraron líneas huérfanas. Nada que hacer.")
        return

    _logger.info("PRS repair: encontradas %d líneas huérfanas para reparar.", len(orphans))

    affected_statements = Statement.browse()
    skipped = []

    for line in orphans:
        journal_id = line.journal_id.id
        line_date = line.date or fields.Date.today()

        # Candidato principal: estado abierto cuya fecha <= fecha de la línea
        best = Statement.search([
            ('journal_id', '=', journal_id),
            ('prs_state', '=', 'open'),
            ('date', '<=', line_date),
        ], order='date desc, id desc', limit=1)

        if best:
            line.with_context(prs_skip_balance_recompute=True).write(
                {'statement_id': best.id}
            )
            affected_statements |= best
            _logger.info(
                "  · Línea id=%s (diario=%s, fecha=%s, monto=%s) → estado '%s' (id=%s)",
                line.id, line.journal_id.name, line_date, line.amount,
                best.name or best.id, best.id,
            )
            continue

        # Fallback: estado abierto más antiguo del diario
        fallback = Statement.search([
            ('journal_id', '=', journal_id),
            ('prs_state', '=', 'open'),
        ], order='date asc, id asc', limit=1)

        if fallback:
            line.with_context(prs_skip_balance_recompute=True).write(
                {'statement_id': fallback.id}
            )
            affected_statements |= fallback
            _logger.warning(
                "  · Línea id=%s (diario=%s, fecha=%s) → fallback estado '%s' (id=%s)",
                line.id, line.journal_id.name, line_date,
                fallback.name or fallback.id, fallback.id,
            )
        else:
            skipped.append(line.id)
            _logger.warning(
                "  · Línea id=%s (diario=%s, fecha=%s) — SIN estado abierto disponible. "
                "Creá un Estado de Cuenta para ese diario y volvé a ejecutar.",
                line.id, line.journal_id.name, line_date,
            )

    # 2. Recalcular saldos en cadena para todos los estados afectados
    if affected_statements:
        _logger.info(
            "PRS repair: recalculando saldos en %d estado(s) afectado(s)...",
            len(affected_statements),
        )
        try:
            affected_statements._prs_recompute_balances()
        except Exception as e:
            _logger.error("PRS repair: error al recalcular saldos: %s", e)

    # 3. Resumen final
    repaired = len(orphans) - len(skipped)
    _logger.info(
        "PRS repair completado: %d reparadas, %d sin estado disponible (ids: %s).",
        repaired, len(skipped), skipped or 'ninguna',
    )
    if skipped:
        _logger.warning(
            "Las siguientes líneas siguen huérfanas (crear Estado de Cuenta primero): %s",
            skipped,
        )


# ── Punto de entrada al ejecutar como script ──────────────────────────────────
if __name__ == '__main__' or 'env' in dir():
    repair_orphan_lines(env)  # noqa: F821  (env inyectado por odoo shell)
