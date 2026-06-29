/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

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
        const label = _normalizeFacetText(
            facet.querySelector(".o_facet_label")?.textContent || ""
        ).toLowerCase();
        if (label !== "diario") continue;
        const valueNode =
            facet.querySelector(".o_facet_value") ||
            facet.querySelector(".o_facet_values .o_facet_value") ||
            facet.querySelector(".o_facet_values");
        const val = _normalizeFacetText(valueNode?.textContent || "");
        if (val) return val;
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
    const name = _guessJournalNameFromFacets();
    const fromFacet = await _journalIdFromName(env, name);
    if (fromFacet) return fromFacet;
    const ctx = _getCurrentContext(env);
    return _guessJournalIdFromContext(ctx);
}

async function _journalAllowsAccreditation(env, journalId) {
    if (!journalId) return false;
    try {
        const recs = await env.services.orm.searchRead(
            "account.journal",
            [["id", "=", journalId]],
            ["id", "prs_accreditation_control"],
            { limit: 1 }
        );
        return Boolean(recs.length && recs[0].prs_accreditation_control);
    } catch {
        return false;
    }
}

async function _getPendingCount(env, journalId) {
    if (!journalId) return 0;
    try {
        const today = new Date().toISOString().slice(0, 10);
        return await env.services.orm.searchCount("prs.money.flow", [
            ["journal_id", "=", journalId],
            ["state", "in", ["waiting_accreditation", "due"]],
            ["statement_line_id", "=", false],
            ["expected_date", "<=", today],
        ]);
    } catch {
        return 0;
    }
}

const prsAccreditationButtonService = {
    start(env) {
        let currentJournalId = null;
        let isRunning = false;
        let debounceTimer = null;

        function _removeButton() {
            document.querySelectorAll(".o_prs_accreditation_btn").forEach((b) => b.remove());
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
                const existing = document.querySelector(".o_prs_accreditation_btn");

                if (!journalId) {
                    _removeButton();
                    currentJournalId = null;
                    return;
                }

                const allowed = await _journalAllowsAccreditation(env, journalId);
                if (!allowed) {
                    _removeButton();
                    currentJournalId = journalId;
                    return;
                }

                if (existing && journalId === currentJournalId) return;
                if (existing) _removeButton();
                currentJournalId = journalId;

                const count = await _getPendingCount(env, journalId);
                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "btn btn-secondary o_prs_accreditation_btn";
                btn.innerHTML =
                    count > 0
                        ? `<i class="fa fa-credit-card me-1"></i>${_t("Acreditaciones")} <span class="badge bg-danger ms-1">${count}</span>`
                        : `<i class="fa fa-credit-card me-1"></i>${_t("Acreditaciones")}`;

                btn.addEventListener("click", async () => {
                    const jId = await _resolveJournalId(env);
                    if (!jId) {
                        env.services.notification.add(
                            _t("No se pudo detectar el diario actual. Seleccioná un Diario en el filtro de búsqueda y reintentá."),
                            { type: "danger" }
                        );
                        return;
                    }
                    const canOpen = await _journalAllowsAccreditation(env, jId);
                    if (!canOpen) {
                        env.services.notification.add(
                            _t("Este botón solo está disponible en diarios con 'Control de acreditaciones' activo."),
                            { type: "warning" }
                        );
                        _removeButton();
                        return;
                    }
                    const ctx = _getCurrentContext(env);
                    await env.services.action.doAction({
                        type: "ir.actions.act_window",
                        name: _t("Acreditaciones pendientes"),
                        res_model: "prs.accreditation.confirm.wizard",
                        views: [[false, "form"]],
                        target: "new",
                        context: {
                            ...(ctx || {}),
                            default_journal_id: jId,
                            active_journal_id: jId,
                        },
                    });
                });

                // Insertar después de "Transferencia interna" o "Depósitos POS" si existen
                const anchor =
                    buttons.querySelector(".o_prs_pos_deposit_btn") ||
                    buttons.querySelector(".o_prs_internal_transfer_btn");
                if (anchor) {
                    anchor.insertAdjacentElement("afterend", btn);
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

registry
    .category("services")
    .add("prs_accreditation_button_service", prsAccreditationButtonService);
