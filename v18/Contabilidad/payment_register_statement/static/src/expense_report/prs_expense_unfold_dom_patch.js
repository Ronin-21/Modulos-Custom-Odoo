/** @odoo-module **/

/**
 * PRS Expense Report - Dynamic unfold/fold DOM fallback.
 *
 * Problem:
 * - In some Odoo builds, clicking the caret only toggles the UI and does NOT fetch new lines.
 * - If the rendered <tr> does not expose a usable line id/parent id (e.g. data-id="line" everywhere),
 *   the native toggle can't locate descendants, so nothing happens until a full reload.
 *
 * Fix:
 * - For this custom report ("Reporte de gastos") we toggle descendants using the `line_level_N` classes.
 * - We only run this fallback when the clicked row does NOT expose a usable identifier, so native behavior
 *   stays untouched on other reports / builds.
 */

function isExpenseReportPage() {
    const title =
        document.querySelector(".o_control_panel .breadcrumb-item.active")?.textContent?.trim()
        || document.querySelector(".o_control_panel .o_breadcrumb .active")?.textContent?.trim()
        || "";
    return title.toLowerCase().includes("reporte de gastos");
}

function getLevel(tr) {
    const m = (tr.className || "").match(/line_level_(\d+)/);
    return m ? parseInt(m[1], 10) : null;
}

function getCaretIcon(tr) {
    return tr.querySelector("button.btn_foldable i.fa, button.btn_foldable .fa");
}

function isFoldedByIcon(iconEl) {
    return !!iconEl && iconEl.classList.contains("fa-caret-right");
}

function setFoldedIcon(iconEl, folded) {
    if (!iconEl) return;
    iconEl.classList.toggle("fa-caret-right", folded);
    iconEl.classList.toggle("fa-caret-down", !folded);
}

function hideRow(tr) {
    tr.classList.add("o_hidden");
    tr.style.display = "none";
}

function showRow(tr) {
    tr.classList.remove("o_hidden");
    tr.style.display = "";
}

function toggleDescendantsByLevel(anchorTr, fold) {
    const level = getLevel(anchorTr);
    if (!level) return;

    let tr = anchorTr.nextElementSibling;
    while (tr && tr.tagName === "TR") {
        const l = getLevel(tr);
        if (l === null) {
            tr = tr.nextElementSibling;
            continue;
        }
        if (l <= level) break;

        if (fold) {
            hideRow(tr);
            tr = tr.nextElementSibling;
            continue;
        }

        // unfolding: show descendants, but keep descendants of folded intermediate nodes hidden
        showRow(tr);

        const icon = getCaretIcon(tr);
        const foldedIntermediate = isFoldedByIcon(icon);
        if (icon && foldedIntermediate) {
            const intermediateLevel = l;
            let sub = tr.nextElementSibling;
            while (sub && sub.tagName === "TR") {
                const sl = getLevel(sub);
                if (sl === null) {
                    sub = sub.nextElementSibling;
                    continue;
                }
                if (sl <= intermediateLevel) break;
                hideRow(sub);
                sub = sub.nextElementSibling;
            }
            tr = sub;
            continue;
        }

        tr = tr.nextElementSibling;
    }
}

(function install() {
    // Capture to run before other handlers (and optionally stop them only when fallback is used).
    document.addEventListener(
        "click",
        (ev) => {
            const btn = ev.target?.closest?.("button.btn_foldable");
            if (!btn) return;

            const tr = btn.closest("tr");
            if (!tr) return;

            if (!isExpenseReportPage()) return;

            // If the row exposes a usable identifier, let native account_reports handle it.
            const dataId = tr.getAttribute("data-id");
            const dataLineId = tr.getAttribute("data-line-id");
            const hasUsableId =
                (dataLineId && dataLineId !== "line") ||
                (dataId && dataId !== "line");

            if (hasUsableId) return;

            // Fallback: do DOM toggle based on line levels
            ev.preventDefault();
            ev.stopPropagation();

            const icon = getCaretIcon(tr);
            const currentlyFolded = isFoldedByIcon(icon);
            const willFold = !currentlyFolded ? true : false;

            setFoldedIcon(icon, willFold);
            toggleDescendantsByLevel(tr, willFold);
        },
        true
    );
})();
