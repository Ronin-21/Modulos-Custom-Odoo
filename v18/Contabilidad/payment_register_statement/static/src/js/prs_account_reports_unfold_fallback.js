/** @odoo-module **/

/**
 * Fallback fold/unfold for account_reports tables where rows don't carry unique ids.
 *
 * In some Odoo SH builds, the report HTML can render rows with `data-id="line"` for all lines,
 * which prevents the native fold/unfold from finding children.
 *
 * This script toggles visibility by using the `line_level_X` classes (hierarchy by level).
 * It does NOT stop propagation, so the native handler can still update options/state.
 */

function getLevel(tr) {
    const m = (tr.className || "").match(/\bline_level_(\d+)\b/);
    return m ? parseInt(m[1], 10) : null;
}

function getCaretIcon(tr) {
    return tr.querySelector('button.btn_foldable i.fa');
}

function isRowOpen(tr) {
    const v = tr.getAttribute('data-prs-open');
    if (v === '1') return true;
    if (v === '0') return false;
    const icon = getCaretIcon(tr);
    if (icon && icon.classList.contains('fa-caret-down')) return true;
    return false;
}

function setRowOpen(tr, open) {
    tr.setAttribute('data-prs-open', open ? '1' : '0');
    const icon = getCaretIcon(tr);
    if (icon) {
        icon.classList.toggle('fa-caret-down', !!open);
        icon.classList.toggle('fa-caret-right', !open);
    }
}

function needsFallback(tableEl) {
    // If we have proper unique ids, let core handle it.
    if (tableEl.querySelector('tr[data-line-id]')) return false;
    const rows = [...tableEl.querySelectorAll('tr[class*="line_level_"]')];
    if (!rows.length) return false;
    const hasUniqueDataId = rows.some(r => {
        const v = r.getAttribute('data-id');
        return v && v !== 'line';
    });
    return !hasUniqueDataId;
}

function applyVisibility(tableEl) {
    if (!tableEl || !needsFallback(tableEl)) return;

    const rows = [...tableEl.querySelectorAll('tr')];
    const openByLevel = {};

    for (const tr of rows) {
        const lvl = getLevel(tr);
        if (lvl === null) continue;

        // Clear deeper levels when we go up.
        for (const k of Object.keys(openByLevel)) {
            const ik = parseInt(k, 10);
            if (ik >= lvl) delete openByLevel[k];
        }

        if (lvl <= 2) {
            tr.style.display = '';
            // Track open state for this level (group/payment lines).
            openByLevel[String(lvl)] = isRowOpen(tr);
            continue;
        }

        // Visible only if all ancestors are open.
        let visible = true;
        for (let a = 2; a < lvl; a++) {
            if (openByLevel[String(a)] === false) {
                visible = false;
                break;
            }
        }

        tr.style.display = visible ? '' : 'none';
        openByLevel[String(lvl)] = isRowOpen(tr);
    }
}

function toggleFromRow(tr) {
    const tableEl = tr.closest('table');
    if (!tableEl || !needsFallback(tableEl)) return;

    const lvl = getLevel(tr);
    if (lvl === null) return;

    const open = !isRowOpen(tr);
    setRowOpen(tr, open);

    // Recompute visibility for the whole table; it's safer with nested folds.
    applyVisibility(tableEl);
}

function findReportTableFromEvent(ev) {
    const target = ev.target;
    if (!target) return null;
    const page = target.closest('.o_account_reports_page');
    if (!page) return null;
    // account_reports table
    return page.querySelector('table');
}

function initObserver(pageEl) {
    if (!pageEl) return;
    const obs = new MutationObserver(() => {
        const tableEl = pageEl.querySelector('table');
        if (tableEl) applyVisibility(tableEl);
    });
    obs.observe(pageEl, { childList: true, subtree: true });
}

(function boot() {
    document.addEventListener('click', (ev) => {
        const btn = ev.target.closest && ev.target.closest('button.btn_foldable');
        if (!btn) return;
        const tr = btn.closest('tr');
        if (!tr) return;
        // Let core run first, then apply our fallback.
        setTimeout(() => toggleFromRow(tr), 0);
    }, true);

    const pageEl = document.querySelector('.o_account_reports_page');
    if (pageEl) {
        initObserver(pageEl);
        const tableEl = pageEl.querySelector('table');
        if (tableEl) applyVisibility(tableEl);
    }
})();
