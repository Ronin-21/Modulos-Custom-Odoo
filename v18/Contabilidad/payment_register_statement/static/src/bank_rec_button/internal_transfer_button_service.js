/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

/**
 * Add a "Transferencia interna" button next to the standard buttons
 * in the Bank Reconciliation widget (OWL view).
 *
 * This view is OWL (account_accountant), so we inject via DOM observation.
 * We also pass the current journal in the action context so the wizard can
 * auto-set "Diario origen" (hidden).
 */

function _getCurrentActionContext(env) {
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
    // Common keys in reconciliation / journal actions
    return (
        ctx?.default_source_journal_id ||
        ctx?.default_journal_id ||
        ctx?.journal_id ||
        ctx?.active_journal_id ||
        null
    );
}

function _guessJournalNameFromFacets() {
    // Look for a facet like: "Diario  PM - Banco"
    const facets = document.querySelectorAll(".o_searchview_facet");
    for (const f of facets) {
        const label = f.querySelector(".o_facet_label");
        const values = f.querySelector(".o_facet_values");
        const labelTxt = (label?.textContent || "").trim();
        if (labelTxt.toLowerCase() === "diario") {
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

    // Fallback: derive from "Diario" facet text
    const journalName = _guessJournalNameFromFacets();
    if (!journalName) {
        return null;
    }

    // Best-effort search by name/display_name
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
            // Only in the bank reconciliation widget view
            const bankRecRoot = document.querySelector(".o_bank_rec_widget_kanban_view");
            if (!bankRecRoot) {
                return;
            }
            const buttons = document.querySelector(".o_control_panel_main_buttons");
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

            // Insert before the gear dropdown group if present, so it matches standard buttons
            const gearGroup = buttons.querySelector(".btn-group");
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

registry.category("services").add("prs_internal_transfer_button_service", prsInternalTransferButtonService);
