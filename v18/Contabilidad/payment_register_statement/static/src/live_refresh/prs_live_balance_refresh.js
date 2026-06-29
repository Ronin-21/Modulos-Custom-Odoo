/** @odoo-module **/

import { registry } from "@web/core/registry";

function _getCurrentController(env) {
    return env?.services?.action?.currentController || null;
}

function _getCurrentContext(env) {
    const ctrl = _getCurrentController(env);
    return (
        ctrl?.props?.context ||
        ctrl?.action?.context ||
        ctrl?.env?.config?.context ||
        env?.config?.context ||
        {}
    );
}

function _getCurrentResModel(env) {
    const ctrl = _getCurrentController(env);
    return (
        ctrl?.props?.resModel ||
        ctrl?.props?.model ||
        ctrl?.action?.res_model ||
        ctrl?.props?.context?.active_model ||
        ctrl?.action?.context?.active_model ||
        ""
    );
}

function _isStatementContext(env) {
    const resModel = (_getCurrentResModel(env) || "").toLowerCase();
    return resModel === "account.bank.statement" || resModel === "account.bank.statement.line";
}

function _isBankReconciliationContext() {
    return !!document.querySelector(".o_bank_rec_widget_kanban_view");
}

function _isCashBalanceReportContext(rootEl) {
    const doc = rootEl || document;
    const selectors = [
        ".o_breadcrumb .active",
        ".o_control_panel .breadcrumb-item.active",
        ".o_account_reports_page .o_account_reports_title",
        ".o_account_reports_page h1",
        ".o_account_reports_page h2",
    ];
    for (const sel of selectors) {
        const el = doc.querySelector(sel);
        const txt = (el?.textContent || "").trim().toLowerCase();
        if (txt.includes("balance de caja")) {
            return true;
        }
    }
    return false;
}

function _findReportUpdateButton() {
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
        if (btn) {
            return btn;
        }
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
}

function _isLikelyReconcileClick(target) {
    if (!target?.closest) {
        return false;
    }
    const el = target.closest("button, .btn, .o_boolean_toggle, input[type='checkbox'], .fa, .oi");
    if (!el) {
        return false;
    }
    const txt = [
        el.textContent || "",
        el.getAttribute?.("title") || "",
        el.getAttribute?.("aria-label") || "",
        el.getAttribute?.("data-tooltip") || "",
        el.className || "",
    ].join(" ").toLowerCase();

    if (txt.includes("concili") || txt.includes("reconcil") || txt.includes("match")) {
        return true;
    }

    const btn = el.closest("button, .btn");
    if (btn && btn.classList.contains("btn-success") && btn.querySelector(".fa-check, .oi-check")) {
        return true;
    }

    return false;
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

function _guessJournalNameFromFacets() {
    const facets = document.querySelectorAll(".o_searchview_facet");
    for (const f of facets) {
        const label = f.querySelector(".o_facet_label");
        const values = f.querySelector(".o_facet_values");
        const labelTxt = (label?.textContent || "").trim().toLowerCase();
        if (labelTxt === "diario") {
            const valTxt = (values?.textContent || "").trim();
            if (valTxt) {
                return valTxt;
            }
        }
    }
    return null;
}

async function _guessJournalId(env) {
    const ctx = _getCurrentContext(env);
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

function _normalizeText(txt) {
    return (txt || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function _isLeaf(el) {
    return !!(el && el.nodeType === 1 && el.children.length === 0);
}

function _looksLikeAmountText(txt) {
    const v = (txt || "").replace(/\s+/g, " ").trim();
    return /[$€£¥]/.test(v) || /-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})/.test(v);
}

function _findLeafAmountCandidates(container) {
    if (!container?.querySelectorAll) {
        return [];
    }
    return Array.from(container.querySelectorAll("*"))
        .filter((el) => _isLeaf(el) && _looksLikeAmountText(el.textContent || ""));
}

function _findLabeledAmount(labelMatcher) {
    const bankRecRoot = document.querySelector(".o_bank_rec_widget_kanban_view") || document;
    const nodes = bankRecRoot.querySelectorAll("div, span, strong, b, h1, h2, h3, h4, p, a, td, th, label");
    for (const el of nodes) {
        const txt = _normalizeText(el.textContent || "");
        if (!labelMatcher(txt)) {
            continue;
        }
        let parent = el.parentElement;
        for (let depth = 0; parent && depth < 6; depth += 1, parent = parent.parentElement) {
            const amounts = _findLeafAmountCandidates(parent);
            if (amounts.length >= 1 && amounts.length <= 4) {
                return { labelEl: el, amountEl: amounts[amounts.length - 1], container: parent };
            }
        }
    }
    return null;
}

function _formatMoney(amount, currencySymbol) {
    const n = Number(amount || 0);
    const absFormatted = new Intl.NumberFormat(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(Math.abs(n));
    const sign = n < 0 ? "-" : "";
    return `${currencySymbol || "$"} ${sign}${absFormatted}`;
}

function _setAmountText(target, amount, currencySymbol) {
    if (!target) {
        return;
    }
    const nextText = _formatMoney(amount, currencySymbol);
    if ((target.textContent || "").trim() !== nextText) {
        target.textContent = nextText;
    }
}

registry.category("services").add("prs_live_balance_refresh", {
    start(env) {
        let lastSoftReloadAt = 0;
        let lastReportRefreshAt = 0;
        let lastSidebarRefreshAt = 0;
        let sidebarRefreshPromise = null;

        const softReloadStatement = () => {
            const now = Date.now();
            if (now - lastSoftReloadAt < 1200) {
                return;
            }
            lastSoftReloadAt = now;
            try {
                env.services.action.doAction({ type: "ir.actions.client", tag: "soft_reload" });
            } catch (_) {
                // silent
            }
        };

        const refreshCashBalanceReport = () => {
            const now = Date.now();
            if (now - lastReportRefreshAt < 1200) {
                return;
            }
            lastReportRefreshAt = now;
            const btn = _findReportUpdateButton();
            if (btn) {
                btn.click();
            }
        };

        const refreshBankRecSidebar = async () => {
            if (!_isBankReconciliationContext()) {
                return;
            }
            const now = Date.now();
            if (sidebarRefreshPromise || now - lastSidebarRefreshAt < 500) {
                return;
            }
            lastSidebarRefreshAt = now;

            sidebarRefreshPromise = (async () => {
                try {
                    const journalId = await _guessJournalId(env);
                    if (!journalId) {
                        return;
                    }
                    const data = await env.services.orm.call(
                        "account.journal",
                        "prs_get_reconciliation_sidebar_data",
                        [[journalId]],
                        {}
                    );
                    if (!data || (!data.only_reconciled && !data.auto_statement_balance)) {
                        return;
                    }

                    const balanceRow = _findLabeledAmount((txt) => txt === "balance");
                    if (balanceRow?.amountEl) {
                        _setAmountText(balanceRow.amountEl, data.general_balance, data.currency_symbol);
                    }

                    const statementRow = _findLabeledAmount((txt) => txt.includes("estado de cuenta"));
                    if (statementRow?.labelEl && statementRow?.amountEl) {
                        const labelText = statementRow.labelEl.textContent || "";
                        if (!data.statement_date || labelText.includes(data.statement_date)) {
                            _setAmountText(statementRow.amountEl, data.statement_balance, data.currency_symbol);
                        }
                    }
                } catch (_) {
                    // silent: nunca romper la conciliación por una actualización visual
                } finally {
                    sidebarRefreshPromise = null;
                }
            })();

            await sidebarRefreshPromise;
        };

        const scheduleSidebarRefresh = (delay = 0) => {
            window.setTimeout(() => {
                refreshBankRecSidebar();
            }, delay);
        };

        const onClick = (ev) => {
            if (_isStatementContext(env) && _isLikelyReconcileClick(ev.target)) {
                window.setTimeout(() => softReloadStatement(), 250);
                scheduleSidebarRefresh(700);
                return;
            }
            if (_isBankReconciliationContext()) {
                scheduleSidebarRefresh(250);
            }
        };

        const onFocusLike = () => {
            if (_isCashBalanceReportContext(document)) {
                window.setTimeout(() => refreshCashBalanceReport(), 0);
            }
            if (_isBankReconciliationContext()) {
                scheduleSidebarRefresh(0);
            }
        };

        const observer = new MutationObserver(() => {
            if (_isBankReconciliationContext()) {
                scheduleSidebarRefresh(150);
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });

        document.addEventListener("click", onClick, true);
        window.addEventListener("focus", onFocusLike, true);
        document.addEventListener("visibilitychange", onFocusLike, true);
        scheduleSidebarRefresh(300);

        return {
            destroy() {
                observer.disconnect();
                document.removeEventListener("click", onClick, true);
                window.removeEventListener("focus", onFocusLike, true);
                document.removeEventListener("visibilitychange", onFocusLike, true);
            },
        };
    },
});
