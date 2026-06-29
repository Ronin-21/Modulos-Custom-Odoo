/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

/**
 * Inyecta el botón "Depósitos POS" en el tablero de conciliación bancaria.
 *
 * Regla funcional:
 * - El botón SOLO se muestra en el diario/caja destino que tenga activado
 *   `prs_pos_deposit_require_validation`.
 * - No se muestra en las cajas POS de origen.
 */

function _getCurrentContext(env) {
    const ctrl = env?.services?.action?.currentController;
    return (
        ctrl?.props?.context ||
        ctrl?.action?.context ||
        ctrl?.env?.config?.context ||
        env?.config?.context ||
        {}
    );
}

function _guessJournalIdFromContext(ctx) {
    return (
        ctx?.default_source_journal_id ||
        ctx?.default_journal_id ||
        ctx?.journal_id ||
        ctx?.active_journal_id ||
        null
    );
}

function _normalizeFacetText(text) {
    return (text || "")
        .replace(/[×x]\s*$/i, "")
        .replace(/\s+/g, " ")
        .trim();
}

function _guessJournalNameFromFacets() {
    const facets = document.querySelectorAll(".o_searchview_facet");
    for (const facet of facets) {
        const label = _normalizeFacetText(facet.querySelector(".o_facet_label")?.textContent || "").toLowerCase();
        if (label !== "diario") {
            continue;
        }

        const valueNode =
            facet.querySelector(".o_facet_value") ||
            facet.querySelector(".o_facet_values .o_facet_value") ||
            facet.querySelector(".o_facet_values");
        const val = _normalizeFacetText(valueNode?.textContent || "");
        if (val) {
            return val;
        }
    }
    return null;
}

async function _journalIdFromName(env, name) {
    if (!name) return null;
    const orm = env.services.orm;
    let recs = await orm.searchRead(
        "account.journal",
        [["type", "in", ["bank", "cash"]], ["name", "=", name]],
        ["id"],
        { limit: 1 }
    );
    if (!recs.length) {
        recs = await orm.searchRead(
            "account.journal",
            [["type", "in", ["bank", "cash"]], ["display_name", "ilike", name]],
            ["id"],
            { limit: 1 }
        );
    }
    return recs.length ? recs[0].id : null;
}

async function _resolveJournalId(env) {
    // Prioridad al facet visible: al cambiar de diario en conciliación, el
    // contexto de la acción puede quedar viejo, pero el facet refleja la caja real.
    const name = _guessJournalNameFromFacets();
    const fromFacet = await _journalIdFromName(env, name);
    if (fromFacet) return fromFacet;

    const ctx = _getCurrentContext(env);
    return _guessJournalIdFromContext(ctx);
}

async function _journalAllowsPosDepositButton(env, journalId) {
    if (!journalId) return false;
    try {
        const recs = await env.services.orm.searchRead(
            "account.journal",
            [["id", "=", journalId], ["type", "in", ["bank", "cash"]]],
            ["id", "prs_pos_deposit_require_validation"],
            { limit: 1 }
        );
        return Boolean(recs.length && recs[0].prs_pos_deposit_require_validation);
    } catch {
        return false;
    }
}

async function _hasPending(env, journalId) {
    if (!journalId) return false;
    try {
        const count = await env.services.orm.searchCount("pos.cash.transfer", [
            ["prs_pending_validation", "=", true],
            ["destination_journal_id", "=", journalId],
        ]);
        return count > 0;
    } catch {
        return false;
    }
}

const prsPosDepositButtonService = {
    start(env) {
        let currentJournalId = null;
        let isRunning = false;
        let debounceTimer = null;

        function _removeButton() {
            document.querySelectorAll(".o_prs_pos_deposit_btn").forEach((b) => b.remove());
        }

        async function ensureButton() {
            if (isRunning) return;
            isRunning = true;

            try {
                if (!document.querySelector(".o_bank_rec_widget_kanban_view")) {
                    _removeButton();
                    currentJournalId = null;
                    return;
                }

                const buttons = document.querySelector(".o_control_panel_main_buttons");
                if (!buttons) return;

                const journalId = await _resolveJournalId(env);
                const existing = document.querySelector(".o_prs_pos_deposit_btn");

                if (!journalId) {
                    _removeButton();
                    currentJournalId = null;
                    return;
                }

                const allowed = await _journalAllowsPosDepositButton(env, journalId);
                if (!allowed) {
                    _removeButton();
                    currentJournalId = journalId;
                    return;
                }

                if (existing && journalId === currentJournalId) {
                    return;
                }
                if (existing) {
                    _removeButton();
                }
                currentJournalId = journalId;

                const hasPending = await _hasPending(env, journalId);
                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "btn btn-secondary o_prs_pos_deposit_btn";
                btn.innerHTML = hasPending
                    ? `<i class="fa fa-arrow-down me-1"></i>${_t("Depósitos POS")} <span class="badge bg-danger ms-1">!</span>`
                    : `<i class="fa fa-arrow-down me-1"></i>${_t("Depósitos POS")}`;

                btn.addEventListener("click", async () => {
                    const jId = await _resolveJournalId(env);
                    if (!jId) {
                        env.services.notification.add(
                            _t("No se pudo detectar el diario actual."),
                            { type: "danger" }
                        );
                        return;
                    }
                    const canOpen = await _journalAllowsPosDepositButton(env, jId);
                    if (!canOpen) {
                        env.services.notification.add(
                            _t("Este botón solo está disponible en la caja destino configurada para validar depósitos POS."),
                            { type: "warning" }
                        );
                        _removeButton();
                        return;
                    }
                    const ctx = _getCurrentContext(env);
                    await env.services.action.doAction({
                        type: "ir.actions.act_window",
                        name: _t("Depósitos POS pendientes"),
                        res_model: "prs.pos.deposit.confirm.wizard",
                        views: [[false, "form"]],
                        target: "new",
                        context: {
                            ...(ctx || {}),
                            default_journal_id: jId,
                            active_journal_id: jId,
                        },
                    });
                });

                const transferBtn = buttons.querySelector(".o_prs_internal_transfer_btn");
                if (transferBtn) {
                    transferBtn.insertAdjacentElement("afterend", btn);
                } else {
                    const gearGroup = buttons.querySelector(".btn-group");
                    if (gearGroup && gearGroup.parentElement === buttons) {
                        buttons.insertBefore(btn, gearGroup);
                    } else {
                        buttons.appendChild(btn);
                    }
                }
            } finally {
                isRunning = false;
            }
        }

        function scheduledEnsure() {
            if (debounceTimer) clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                debounceTimer = null;
                ensureButton();
            }, 150);
        }

        const observer = new MutationObserver(() => {
            if (!document.querySelector(".o_bank_rec_widget_kanban_view")) {
                _removeButton();
                currentJournalId = null;
                return;
            }
            scheduledEnsure();
        });

        observer.observe(document.body, { childList: true, subtree: true });
        scheduledEnsure();

        return {
            stop() {
                observer.disconnect();
                if (debounceTimer) clearTimeout(debounceTimer);
                _removeButton();
            },
        };
    },
};

registry.category("services").add("prs_pos_deposit_button_service", prsPosDepositButtonService);
