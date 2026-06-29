/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";

export class PRSInternalTransferCogMenu extends Component {
    static template = "payment_register_statement.PRSInternalTransferCogMenu";
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
        const ctrl = this.actionService?.currentController;
        return (
            ctrl?.props?.context ||
            ctrl?.action?.context ||
            ctrl?.env?.config?.context ||
            this.env?.config?.context ||
            {}
        );
    }

    _guessJournalNameFromFacets() {
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

    async _guessSourceJournalId(ctx) {
        const fromCtx = (
            ctx?.default_source_journal_id ||
            ctx?.default_journal_id ||
            ctx?.journal_id ||
            ctx?.active_journal_id ||
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
        const tag = c.tag || "";
        // Mostrar en el widget de conciliación bancaria (varios modelos/tags posibles en Odoo 18)
        return (
            resModel === "account.bank.statement.line" ||
            resModel === "account.bank.statement" ||
            tag === "bank_rec_widget" ||
            tag.includes("bank_rec") ||
            !!document.querySelector(".o_bank_rec_widget_kanban_view")
        );
    },
};

registry.category("cogMenu").add("prs_internal_transfer_cog_menu_item", PRSInternalTransferCogMenuItem);


// ── Cajas Registradoras en el cog menu ────────────────────────────────────────

export class PRSCashRegisterCogMenu extends Component {
    static template = "payment_register_statement.PRSCashRegisterCogMenu";
    static components = { DropdownItem };
    static props = {};

    setup() {
        this.actionService = useService("action");
        this.orm = useService("orm");
    }

    get label() {
        return _t("Cajas Registradoras");
    }

    _getCurrentContext() {
        const ctrl = this.actionService?.currentController;
        return (
            ctrl?.props?.context ||
            ctrl?.action?.context ||
            ctrl?.env?.config?.context ||
            this.env?.config?.context ||
            {}
        );
    }

    _guessJournalIdFromFacets() {
        const facets = document.querySelectorAll(".o_searchview_facet");
        for (const f of facets) {
            const label = f.querySelector(".o_facet_label");
            const labelTxt = (label?.textContent || "").trim().toLowerCase();
            if (labelTxt === "diario") {
                const val = f.querySelector(".o_facet_values");
                return (val?.textContent || "").trim() || null;
            }
        }
        return null;
    }

    async onSelected() {
        const ctx = this._getCurrentContext();

        // Obtener journal_id desde el contexto o desde el filtro de búsqueda activo
        let journalId =
            ctx?.default_journal_id ||
            ctx?.journal_id ||
            ctx?.active_journal_id ||
            null;

        if (!journalId) {
            const journalName = this._guessJournalIdFromFacets();
            if (journalName) {
                const recs = await this.orm.searchRead(
                    "account.journal",
                    [["type", "in", ["bank", "cash"]], ["display_name", "ilike", journalName]],
                    ["id"],
                    { limit: 1 }
                );
                journalId = recs.length ? recs[0].id : null;
            }
        }

        // Abrir la vista Cajas Registradoras filtrada por el diario actual (si lo conocemos)
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            name: _t("Cajas Registradoras"),
            res_model: "account.bank.statement",
            views: [[false, "list"], [false, "form"]],
            view_mode: "list,form",
            target: "current",
            domain: journalId ? [["journal_id", "=", journalId]] : [],
            context: {
                ...(ctx || {}),
                ...(journalId ? { default_journal_id: journalId } : {}),
            },
        });
    }
}

export const PRSCashRegisterCogMenuItem = {
    Component: PRSCashRegisterCogMenu,
    groupNumber: 30,
    isDisplayed: ({ config } = {}) => {
        const c = config || {};
        const resModel = c.resModel || c.model || "";
        const tag = c.tag || "";
        return (
            resModel === "account.bank.statement.line" ||
            resModel === "account.bank.statement" ||
            tag === "bank_rec_widget" ||
            tag.includes("bank_rec") ||
            !!document.querySelector(".o_bank_rec_widget_kanban_view")
        );
    },
};

registry.category("cogMenu").add("prs_cash_register_cog_menu_item", PRSCashRegisterCogMenuItem);
