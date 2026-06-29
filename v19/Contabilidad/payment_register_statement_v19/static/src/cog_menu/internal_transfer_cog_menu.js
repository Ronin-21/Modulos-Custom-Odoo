/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";

const FACET_SELECTORS = [
    ".o_searchview_facet",
    ".o_search_bar .o_searchview_facet",
    ".o_cp_searchview .o_searchview_facet",
];

export class PRSInternalTransferCogMenu extends Component {
    static template = "payment_register_statement_v19.PRSInternalTransferCogMenu";
    static components = { DropdownItem };
    static props = {};

    setup() {
        this.actionService = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    get label() {
        return _t("Transferencia interna");
    }

    _getCurrentContext() {
        const ctrl = this.actionService?.currentController || this.actionService?.currentControllerRef;
        return (
            ctrl?.props?.context ||
            ctrl?.action?.context ||
            ctrl?.env?.config?.context ||
            this.env?.config?.context ||
            {}
        );
    }

    _guessJournalNameFromFacets() {
        const facets = document.querySelectorAll(FACET_SELECTORS.join(","));
        for (const f of facets) {
            const label = f.querySelector(".o_facet_label, .o_searchview_facet_label");
            const values = f.querySelector(".o_facet_values, .o_searchview_facet_values");
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

    async _guessSourceJournalId(ctx) {
        const fromCtx = (
            ctx?.default_source_journal_id ||
            ctx?.default_journal_id ||
            ctx?.journal_id ||
            ctx?.active_journal_id ||
            ctx?.default_st_line_journal_id ||
            null
        );
        if (fromCtx) {
            return fromCtx;
        }
        const journalName = this._guessJournalNameFromFacets();
        if (!journalName) {
            return null;
        }
        let recs = await this.orm.searchRead(
            "account.journal",
            [["type", "in", ["bank", "cash"]], ["name", "=", journalName]],
            ["id"],
            { limit: 2 }
        );
        if (!recs.length) {
            recs = await this.orm.searchRead(
                "account.journal",
                [["type", "in", ["bank", "cash"]], ["display_name", "ilike", journalName]],
                ["id"],
                { limit: 1 }
            );
        }
        return recs.length ? recs[0].id : null;
    }

    async onSelected() {
        const ctx = this._getCurrentContext();
        const sourceJournalId = await this._guessSourceJournalId(ctx);
        if (!sourceJournalId) {
            this.notification.add(
                _t("No se pudo detectar el diario actual. Seleccione un Diario en la búsqueda (filtro 'Diario') y reintente."),
                { type: "danger" }
            );
            return;
        }

        await this.actionService.doAction({
            type: "ir.actions.act_window",
            name: this.label,
            res_model: "prs.internal.transfer.wizard",
            views: [[false, "form"]],
            target: "new",
            context: {
                ...(ctx || {}),
                default_source_journal_id: sourceJournalId,
            },
        });
    }
}

export const PRSInternalTransferCogMenuItem = {
    Component: PRSInternalTransferCogMenu,
    groupNumber: 30,
    isDisplayed: ({ config } = {}) => {
        const c = config || {};
        const resModel = c.resModel || c.model || "";
        return (
            resModel === "account.bank.statement.line" ||
            resModel === "account.bank.statement" ||
            resModel.includes("bank_rec_widget") ||
            !!document.querySelector(".o_bank_rec_widget_kanban_view, .o_bank_reconciliation, .o_account_reconciliation")
        );
    },
};

registry.category("cogMenu").add("prs_internal_transfer_cog_menu_item", PRSInternalTransferCogMenuItem, { force: true });
