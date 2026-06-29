/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

const BANK_REC_ROOT_SELECTORS = [
    ".o_bank_rec_widget_kanban_view",
    ".o_bank_reconciliation",
    ".o_account_reconciliation",
    ".o_action_manager .o_content:has(.o_bank_rec_widget_kanban_view)",
];

const CONTROL_PANEL_BUTTON_SELECTORS = [
    ".o_control_panel_main_buttons",
    ".o_cp_buttons",
    ".o_control_panel .o_cp_buttons",
];

const FACET_SELECTORS = [
    ".o_searchview_facet",
    ".o_search_bar .o_searchview_facet",
    ".o_cp_searchview .o_searchview_facet",
];

function _queryFirst(selectors, root = document) {
    for (const selector of selectors) {
        const el = root.querySelector(selector);
        if (el) {
            return el;
        }
    }
    return null;
}

function _getCurrentActionContext(env) {
    const actionService = env?.services?.action;
    const ctrl = actionService?.currentController || actionService?.currentControllerRef || null;
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
        ctx?.default_st_line_journal_id ||
        null
    );
}

function _guessJournalNameFromFacets() {
    const selectors = FACET_SELECTORS.flatMap((s) => [s, `${s} *`]);
    const facets = document.querySelectorAll(selectors.join(","));
    for (const f of facets) {
        const label = f.querySelector?.(".o_facet_label, .o_searchview_facet_label");
        const values = f.querySelector?.(".o_facet_values, .o_searchview_facet_values");
        const labelTxt = (label?.textContent || "").trim().toLowerCase();
        if (labelTxt === "diario" || labelTxt === "journal") {
            const valTxt = (values?.textContent || "").trim();
            if (valTxt) {
                return valTxt;
            }
        }
    }
    return null;
}

async function _guessJournalId(env) {
    const ctx = _getCurrentActionContext(env);
    const fromCtx = _guessJournalIdFromContext(ctx);
    if (fromCtx) {
        return fromCtx;
    }

    const journalName = _guessJournalNameFromFacets();
    if (!journalName) {
        return null;
    }

    const orm = env.services.orm;
    let recs = await orm.searchRead(
        "account.journal",
        [["type", "in", ["bank", "cash"]], ["name", "=", journalName]],
        ["id"],
        { limit: 2 }
    );
    if (!recs.length) {
        recs = await orm.searchRead(
            "account.journal",
            [["type", "in", ["bank", "cash"]], ["display_name", "ilike", journalName]],
            ["id"],
            { limit: 1 }
        );
    }
    return recs.length ? recs[0].id : null;
}

function _buildWizardAction(env, journalId) {
    const ctx = _getCurrentActionContext(env);
    return {
        type: "ir.actions.act_window",
        name: _t("Transferencia interna"),
        res_model: "prs.internal.transfer.wizard",
        views: [[false, "form"]],
        target: "new",
        context: {
            ...(ctx || {}),
            default_source_journal_id: journalId,
        },
    };
}

const prsInternalTransferButtonService = {
    start(env) {
        const ensureButton = () => {
            const bankRecRoot = _queryFirst(BANK_REC_ROOT_SELECTORS);
            if (!bankRecRoot) {
                return;
            }
            const buttons = _queryFirst(CONTROL_PANEL_BUTTON_SELECTORS);
            if (!buttons) {
                return;
            }
            if (buttons.querySelector(".o_prs_internal_transfer_btn")) {
                return;
            }

            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "btn btn-secondary o_prs_internal_transfer_btn";
            btn.textContent = _t("Transferencia interna");

            btn.addEventListener("click", async () => {
                const journalId = await _guessJournalId(env);
                if (!journalId) {
                    env.services.notification.add(
                        _t("No se pudo detectar el diario actual. Seleccione un Diario en la búsqueda (filtro 'Diario') y reintente."),
                        { type: "danger" }
                    );
                    return;
                }
                await env.services.action.doAction(_buildWizardAction(env, journalId));
            });

            const gearGroup = buttons.querySelector(".btn-group, .dropdown, .o_cp_action_menus");
            if (gearGroup && gearGroup.parentElement === buttons) {
                buttons.insertBefore(btn, gearGroup);
            } else {
                buttons.appendChild(btn);
            }
        };

        const observer = new MutationObserver(() => ensureButton());
        observer.observe(document.body, { childList: true, subtree: true });
        ensureButton();

        return {
            stop() {
                observer.disconnect();
            },
        };
    },
};

registry.category("services").add("prs_internal_transfer_button_service", prsInternalTransferButtonService, { force: true });
