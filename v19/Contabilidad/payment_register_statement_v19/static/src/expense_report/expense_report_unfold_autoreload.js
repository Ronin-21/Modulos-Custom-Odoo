/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * PRS - Fix unfold/fold not refreshing dynamically in Account Reports for our "Reporte de gastos".
 *
 * Some builds persist the unfolded state but don't re-render the report lines immediately after clicking
 * the caret (requires manual page refresh). We make it dynamic by triggering the report "Update" action
 * right after a caret click, only for our expense report.
 */
registry.category("services").add("prs_expense_report_unfold_autoreload", {
    start() {
        const isExpenseReportContext = (rootEl) => {
            const doc = rootEl || document;
            const candidates = [
                ".o_breadcrumb .active",
                ".o_control_panel .breadcrumb-item.active",
                ".o_account_reports_page .o_account_reports_title",
                ".o_account_reports_page h1",
                ".o_account_reports_page h2",
            ];
            for (const sel of candidates) {
                const el = doc.querySelector(sel);
                const txt = (el && el.textContent ? el.textContent : "").toLowerCase();
                if (txt.includes("reporte de gastos")) {
                    return true;
                }
            }
            const page = doc.querySelector(".o_account_reports_page");
            if (page) {
                const txt = (page.textContent || "").toLowerCase();
                if (txt.includes("reporte de gastos")) {
                    return true;
                }
            }
            return false;
        };

        const findUpdateButton = () => {
            const scope = document.querySelector(".o_control_panel") || document;
            const selectors = [
                "button.o_account_reports_update",
                "button.o_account_report_update",
                "button[data-name='update']",
                "button[data-action='update']",
                "button[title*='Actualizar']",
                "button[aria-label*='Actualizar']",
                "button[title*='Update']",
                "button[aria-label*='Update']",
            ];
            for (const sel of selectors) {
                const btn = scope.querySelector(sel);
                if (btn) return btn;
            }
            const buttons = Array.from(scope.querySelectorAll("button"));
            for (const b of buttons) {
                const t = ((b.getAttribute("title") || b.getAttribute("aria-label") || "")).toLowerCase();
                if (t.includes("actualizar") || t.includes("update") || t.includes("refresh")) {
                    return b;
                }
                if (b.querySelector(".fa-refresh, .fa-rotate-right, .oi-refresh")) {
                    return b;
                }
            }
            return null;
        };

        const caretSelectors = [
            ".o_account_reports_unfoldable",
            ".o_account_report_unfoldable",
            ".o_account_reports_caret",
            ".o_account_reports_toggle",
            ".o_account_reports_table .fa-caret-right",
            ".o_account_reports_table .fa-caret-down",
        ].join(",");

        const onClick = (ev) => {
            const target = ev.target;
            if (!target || !target.closest) return;
            const caret = target.closest(caretSelectors);
            if (!caret) return;

            if (!isExpenseReportContext(document)) return;

            // Let Odoo persist unfold state first, then force a report refresh.
            window.setTimeout(() => {
                const btn = findUpdateButton();
                if (btn) btn.click();
            }, 0);
        };

        document.addEventListener("click", onClick, true);

        return {
            destroy() {
                document.removeEventListener("click", onClick, true);
            },
        };
    },
});
