/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * PRS - Unfold/Fold fallback for "Reporte de gastos"
 *
 * Si el caret no trae líneas hijas por RPC (y sólo se ve al recargar),
 * este fallback hace el plegado/desplegado en el DOM por niveles (line_level_X).
 * Requiere que el backend YA envíe todas las líneas (pagos/moves) en HTML.
 */
registry.category("services").add("prs_expense_report_unfold_dom_toggle_alt", {
    start() {
        // Global guard: avoid double-binding if multiple fallback files are loaded.
        if (window.__PRS_EXPENSE_UNFOLD_DOM_TOGGLE_STARTED__) {
            return { destroy() {} };
        }
        window.__PRS_EXPENSE_UNFOLD_DOM_TOGGLE_STARTED__ = true;

        window.__PRS_EXPENSE_UNFOLD_FALLBACK_INSTALLED__ = "v18";

        const getRoot = () => document.querySelector(".o_account_reports_page");
        const getLevel = (tr) => {
            if (!tr) return null;
            const m = tr.className && tr.className.match(/\bline_level_(\d+)\b/);
            return m ? parseInt(m[1], 10) : null;
        };
        const hasFoldButton = (tr) => !!tr?.querySelector("button.btn_foldable");
        const getCaretIcon = (tr) => tr?.querySelector("button.btn_foldable i.fa");

        const setCollapsed = (tr, collapsed) => {
            if (!tr) return;
            if (collapsed) tr.dataset.prsCollapsed = "1";
            else delete tr.dataset.prsCollapsed;

            const icon = getCaretIcon(tr);
            if (icon) {
                icon.classList.toggle("fa-caret-right", !!collapsed);
                icon.classList.toggle("fa-caret-down", !collapsed);
            }
        };

        const initCollapsedFromIcons = (tbody) => {
            if (!tbody) return;
            for (const tr of tbody.querySelectorAll("tr")) {
                if (!hasFoldButton(tr)) continue;
                const icon = getCaretIcon(tr);
                const collapsed = !!icon && icon.classList.contains("fa-caret-right");
                if (collapsed) tr.dataset.prsCollapsed = "1";
                else delete tr.dataset.prsCollapsed;
            }
        };

        const recomputeVisibility = (tbody) => {
            if (!tbody) return;
            const rows = Array.from(tbody.querySelectorAll("tr"));
            const stack = [];

            for (const tr of rows) {
                const level = getLevel(tr);
                if (!level) continue;

                while (stack.length && stack[stack.length - 1].level >= level) {
                    stack.pop();
                }

                const hiddenByAncestor = stack.length > 0;
                tr.style.display = hiddenByAncestor ? "none" : "";

                if (hasFoldButton(tr) && tr.dataset.prsCollapsed === "1") {
                    stack.push({ level });
                }
            }
        };

        const toggleRow = (tr) => {
            const tbody = tr?.closest("tbody");
            if (!tbody) return;
            if (!hasFoldButton(tr)) return;

            const currentlyCollapsed = tr.dataset.prsCollapsed === "1";
            setCollapsed(tr, !currentlyCollapsed);
            recomputeVisibility(tbody);
        };

        const onClick = (ev) => {
            const root = getRoot();
            if (!root) return;

            if (ev.target.closest(".btn_dropdown") || ev.target.closest(".btn_action") || ev.target.closest("button.btn_dropdown")) {
                return;
            }

            const foldBtn = ev.target.closest("button.btn_foldable");
            const lineNameCell = ev.target.closest("td.line_name");
            if (!foldBtn && !lineNameCell) return;

            const tr = (foldBtn || lineNameCell)?.closest("tr");
            if (!tr || !hasFoldButton(tr)) return;

            setTimeout(() => toggleRow(tr), 0);
        };

        const onReportRendered = () => {
            const root = getRoot();
            if (!root) return;
            const tbody = root.querySelector("tbody");
            if (!tbody) return;

            initCollapsedFromIcons(tbody);
            recomputeVisibility(tbody);
        };

        setTimeout(onReportRendered, 0);

        const mo = new MutationObserver(() => {
            queueMicrotask(onReportRendered);
        });
        mo.observe(document.body, { childList: true, subtree: true });

        document.addEventListener("click", onClick, true);

        return {
            destroy() {
                document.removeEventListener("click", onClick, true);
                mo.disconnect();
            },
        };
    },
});
