/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * PRS - Instant fold/unfold for the custom "Reporte de gastos".
 *
 * Server-side, we force foldable lines to be unfolded in HTML so the full tree is present.
 * This JS then hides/shows descendants immediately on click (no page reload needed),
 * scoped only to this report by the presence of the CSS class `prs_expense_line` / `prs_income_line` / `prs_cash_balance_line` on <tr>.
 */
registry.category("services").add("prs_expense_report_dom_unfold_toggle", {
    start() {
        // Quick verification in the browser console:
        //   window.__PRS_EXPENSE_UNFOLD_FALLBACK_INSTALLED__
        window.__PRS_EXPENSE_UNFOLD_FALLBACK_INSTALLED__ = "v18";

        const toEl = (t) => (t && t.nodeType === 1 ? t : (t && t.parentElement ? t.parentElement : null));

        const getLevel = (tr) => {
            if (!tr || !tr.className) return null;
            const m = tr.className.match(/(?:^|\s)line_level_(\d+)(?:\s|$)/);
            return m ? parseInt(m[1], 10) : null;
        };

        const isPrsRow = (tr) => !!(tr && tr.classList && (tr.classList.contains("prs_expense_line") || tr.classList.contains("prs_income_line") || tr.classList.contains("prs_cash_balance_line")));
        const isFoldableRow = (tr) => !!(tr && tr.querySelector && tr.querySelector("button.btn_foldable"));

        const setCaret = (tr, folded) => {
            const icon = tr && tr.querySelector ? tr.querySelector("button.btn_foldable i") : null;
            if (icon && icon.classList) {
                icon.classList.toggle("fa-caret-right", folded);
                icon.classList.toggle("fa-caret-down", !folded);
            }
        };

        const setFoldedFlag = (tr, folded) => {
            if (!tr || !tr.classList) return;
            // Keep in sync with account_reports conventions.
            tr.classList.toggle("unfolded", !folded);
            setCaret(tr, folded);
        };

        const isFolded = (tr) => {
            if (!tr) return true;
            const icon = tr.querySelector ? tr.querySelector("button.btn_foldable i") : null;
            if (icon && icon.classList) {
                if (icon.classList.contains("fa-caret-right")) return true;
                if (icon.classList.contains("fa-caret-down")) return false;
            }
            // Fallback to class
            return !(tr.classList && tr.classList.contains("unfolded"));
        };

        const iterDescendants = (tr) => {
            const base = getLevel(tr);
            if (!base) return [];
            const out = [];
            let n = tr.nextElementSibling;
            while (n) {
                if (!isPrsRow(n)) break; // stop when leaving our report block
                const lvl = getLevel(n);
                if (!lvl) { n = n.nextElementSibling; continue; }
                if (lvl <= base) break;
                out.push(n);
                n = n.nextElementSibling;
            }
            return out;
        };

        const applyVisibility = (tbody) => {
            if (!tbody) return;

            const rows = Array.from(tbody.querySelectorAll("tr.prs_expense_line, tr.prs_income_line, tr.prs_cash_balance_line"));
            const stack = [];
            for (const tr of rows) {
                const lvl = getLevel(tr);
                if (!lvl) continue;

                // Pop ancestors that ended.
                while (stack.length && stack[stack.length - 1].level >= lvl) stack.pop();

                // Determine if any ancestor is folded.
                const hiddenByAncestor = stack.some((x) => x.folded);
                if (hiddenByAncestor) {
                    tr.style.display = "none";
                } else {
                    // Keep current row display unless explicitly folded by its direct parent action.
                    if (tr.style.display === "none") tr.style.display = "";
                }

                if (isFoldableRow(tr)) {
                    stack.push({ level: lvl, folded: isFolded(tr) });
                }
            }
        };

        const initOncePerTbody = (tbody) => {
            if (!tbody || !tbody.dataset) return;
            if (tbody.dataset.prsFoldInit === "1") return;
            tbody.dataset.prsFoldInit = "1";

            // Default: fold everything (like standard reports), user drills down with caret.
            const foldables = Array.from(tbody.querySelectorAll("tr.prs_expense_line button.btn_foldable, tr.prs_income_line button.btn_foldable, tr.prs_cash_balance_line button.btn_foldable"))
                .map((b) => b.closest("tr"))
                .filter((tr) => !!tr);

            for (const tr of foldables) {
                setFoldedFlag(tr, true);
                for (const d of iterDescendants(tr)) d.style.display = "none";
            }
            applyVisibility(tbody);
        };

        const findAndInit = () => {
            // Find any report tables containing our lines.
            const tbodies = Array.from(document.querySelectorAll("tbody")).filter((tb) =>
                tb.querySelector && tb.querySelector("tr.prs_expense_line, tr.prs_income_line, tr.prs_cash_balance_line")
            );
            for (const tb of tbodies) initOncePerTbody(tb);
        };

        const onClick = (ev) => {
            const target = toEl(ev.target);
            if (!target || !target.closest) return;

            // ignore dropdown action menu clicks
            if (target.closest("button.btn_dropdown")) return;

            const tr = target.closest("tr");
            if (!isPrsRow(tr) || !isFoldableRow(tr)) return;

            // react to clicks on caret button OR on the line name cell
            const hit = target.closest("button.btn_foldable, td.line_name, td.line_name *");
            if (!hit) return;

            const tbody = tr.parentElement;
            if (!tbody) return;

            // IMPORTANT: stop the default account_reports fold/unfold (it triggers a rerender
            // that breaks our client-side folding behavior).
            ev.preventDefault();
            ev.stopPropagation();
            if (typeof ev.stopImmediatePropagation === "function") {
                ev.stopImmediatePropagation();
            }

            const currentlyFolded = isFolded(tr);
            const nextFolded = !currentlyFolded;

            setFoldedFlag(tr, nextFolded);

            const descendants = iterDescendants(tr);
            for (const row of descendants) row.style.display = nextFolded ? "none" : "";

            applyVisibility(tbody);
        };

        // Global click handler (capture so we run even if inner handlers stop bubbling).
        document.addEventListener("click", onClick, true);

        // Init now and whenever account_reports rerenders the table.
        findAndInit();
        const mo = new MutationObserver(() => findAndInit());
        mo.observe(document.body, { childList: true, subtree: true });
    },
});
