/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * PRS - Custom filters for "Reporte de gastos" (Account Reports).
 *
 * Shows two filters in the report topbar (same row as Fecha/Comparación/Diarios/...):
 *  - Método de pago (Pagos salientes): options.prs_payment_method_lines (server-computed from selected journals)
 *  - Tipo de gasto: all | misc | vendor_bill
 *
 * This implementation is deliberately DOM-based (like the rest of this module) to avoid
 * coupling to internal account_reports components. It mutates the live `options` object
 * and triggers a refresh via the current controller/model when possible.
 */
registry.category("services").add("prs_expense_report_custom_filters", {
    start(env) {
        // Debug flag (helps confirm the asset is loaded)
        try {
            window.__PRS_EXPENSE_FILTERS_LOADED__ = true;
        } catch (_e) {}

        // ------------------------------------------------------------
        // Context detection
        // ------------------------------------------------------------
        const isExpenseReportContext = (options) => {
            // 1) Strongest marker: our custom keys exist in the options payload.
            if (options && ("prs_group_mode" in options || "prs_filter_payment_method_line_enabled" in options || "prs_filter_expense_type_enabled" in options)) {
                return true;
            }

            // 2) Strong marker: our handler adds this class on report lines.
            if (document.querySelector("tr.prs_expense_line")) return true;

            // 3) Fallback: title/breadcrumb contains "Reporte de gastos".
            const candidates = [
                ".o_control_panel .breadcrumb-item.active",
                ".o_control_panel .o_cp_title",
                ".o_control_panel .o_breadcrumb",
                ".o_action_manager .o_control_panel .breadcrumb",
                ".o_action_manager .o_control_panel",
            ];
            for (const sel of candidates) {
                const el = document.querySelector(sel);
                const txt = (el?.textContent || "").toLowerCase();
                if (txt.includes("reporte de gastos")) return true;
            }
            return false;
        };

        // ------------------------------------------------------------
        // Live options resolver (heuristic)
        // ------------------------------------------------------------
        // In account_reports the options object can be a Proxy / reactive object.
        // We only need it to be an object with readable keys (no need to enforce plain Object).
        const isOptionsObject = (o) => !!(o && typeof o === "object" && !Array.isArray(o) && !o.nodeType);

        const scoreOptions = (o) => {
            if (!isOptionsObject(o)) return 0;
            let s = 0;
            if ("date" in o) s += 3;
            if ("journals" in o) s += 3;
            if ("unfolded_lines" in o) s += 2;
            if ("unfold_all" in o) s += 1;
            if ("search_term" in o) s += 1;
            if ("comparison" in o) s += 1;
            if ("report_id" in o) s += 2;
            // Our custom keys (very reliable once loaded)
            if ("prs_group_mode" in o) s += 2;
            if ("prs_expense_type" in o) s += 4;
            if ("prs_payment_method_lines" in o) s += 4;
            if ("prs_payment_method_line_id" in o || "prs_payment_method_line_ids" in o) s += 3;
            if ("prs_filter_payment_method_line_enabled" in o) s += 2;
            if ("prs_filter_expense_type_enabled" in o) s += 2;
            return s;
        };

        const findBestOptionsObject = (root) => {
            const visited = new Set();
            let best = null;
            let bestScore = 0;

            const walk = (node, depth) => {
                if (!node || typeof node !== "object") return;
                if (visited.has(node)) return;
                visited.add(node);
                if (depth > 6) return;

                const s = scoreOptions(node);
                if (s > bestScore) {
                    bestScore = s;
                    best = node;
                }

                if (Array.isArray(node)) {
                    for (let i = 0; i < Math.min(node.length, 20); i++) {
                        walk(node[i], depth + 1);
                    }
                    return;
                }

                for (const k of Object.keys(node)) {
                    const v = node[k];
                    if (!v || typeof v !== "object") continue;
                    if (v.nodeType) continue; // skip DOM
                    walk(v, depth + 1);
                }
            };

            walk(root, 0);
            return best;
        };

        const getCurrentController = () => {
            const act = env?.services?.action;
            if (!act) return null;
            try {
                return (
                    act.currentController ||
                    act._currentController ||
                    act.controller ||
                    (typeof act.getCurrentController === "function" ? act.getCurrentController() : null)
                );
            } catch (_e) {
                return null;
            }
        };

        const getLiveOptions = () => {
            const ctrl = getCurrentController();
            if (!ctrl) return null;

            const directCandidates = [
                ctrl?.props?.options,
                ctrl?.props?.reportOptions,
                ctrl?.model?.options,
                ctrl?.model?.reportOptions,
                ctrl?.options,
                ctrl?.reportOptions,
            ].filter(Boolean);

            for (const c of directCandidates) {
                if (scoreOptions(c) >= 6) return c;
            }

            const best = findBestOptionsObject(ctrl);
            return best && scoreOptions(best) >= 6 ? best : null;
        };

        // ------------------------------------------------------------
        // Trigger report refresh (best-effort)
        // ------------------------------------------------------------
        const triggerRefresh = async () => {
            const ctrl = getCurrentController();
            if (!ctrl) return;

            const options = getLiveOptions();
            // options might be null in early stages; still try reload.

            const tryCall = async (fn) => {
                try {
                    const res = fn();
                    if (res && typeof res.then === "function") {
                        await res;
                    }
                    return true;
                } catch (_e) {
                    return false;
                }
            };

            // Common patterns seen in account_reports controllers/models across versions.
            const attempts = [
                () => ctrl.update?.(options),
                () => ctrl.update?.({ options }),
                () => ctrl.reload?.(),
                () => ctrl.model?.load?.(options),
                () => ctrl.model?.load?.({ options }),
                () => ctrl.model?.update?.(options),
                () => ctrl.model?.update?.({ options }),
                () => ctrl.model?.reload?.(),
                () => ctrl.render?.(),
            ];

            for (const a of attempts) {
                // Only try defined callables
                if (typeof a !== "function") continue;
                const ok = await tryCall(a);
                if (ok) return;
            }

            // Ultimate fallback: click the standard "Actualizar/Update" button if present.
            const btn =
                document.querySelector("button[data-name='update']") ||
                document.querySelector("button[data-action='update']") ||
                Array.from(document.querySelectorAll("button")).find((b) => (b.textContent || "").toLowerCase().includes("actualizar"));
            try {
                btn?.click();
            } catch (_e) {
                // no-op
            }
        };

        // ------------------------------------------------------------
        // Topbar host finder
        // ------------------------------------------------------------
        const findTopbarHost = () => {
            const cp = document.querySelector(".o_control_panel");
            if (!cp) return null;

            // Account reports topbar: find the row that already contains the standard filter chips.
            // We anchor on the date button (calendar icon) when present.
            const dateIcon = cp.querySelector(
                "button i.fa-calendar, button i.fa-calendar-o, button i.fa-regular.fa-calendar, button i.fa-calendar-days, button i.fa-solid.fa-calendar"
            );
            const dateBtn = dateIcon?.closest("button");
            if (dateBtn) {
                const group = dateBtn.closest(".btn-group") || dateBtn.parentElement;
                const row = group?.parentElement;
                if (row && row.querySelectorAll("button").length >= 3) {
                    return row;
                }
            }

            const candidates = [
                cp.querySelector(".o_cp_bottom_left"),
                cp.querySelector(".o_cp_searchview"),
                cp.querySelector(".o_cp_bottom"),
                cp,
            ].filter(Boolean);

            const score = (el) => {
                let s = 0;
                if (el.querySelector(".o_searchview") || el.querySelector("input")) s += 3;
                const btns = el.querySelectorAll("button");
                s += Math.min(btns.length, 12);
                if (el.querySelector("i.fa-cog") || el.querySelector("i[title*='Ajustes']")) s += 6;
                // Prefer containers already holding filter chips (lots of buttons with icons)
                const iconBtns = Array.from(btns).filter((b) => b.querySelector && b.querySelector("i.fa, i.fas, i.fa-solid"));
                s += Math.min(iconBtns.length, 8);
                return s;
            };

            let best = null;
            let bestScore = 0;
            for (const el of candidates) {
                const sc = score(el);
                if (sc > bestScore) {
                    bestScore = sc;
                    best = el;
                }
            }
            return best;
        };

        const findSettingsButton = (scope) => {
            const root = scope || document;
            // Account reports usually has a gear icon.
            const byIcon = root.querySelector("button i.fa-cog")?.closest("button");
            if (byIcon) return byIcon;
            // Sometimes it's a dropdown/btn with aria-label
            const byAria = Array.from(root.querySelectorAll("button")).find((b) => {
                const t = ((b.getAttribute("aria-label") || "") + " " + (b.getAttribute("title") || "") + " " + (b.textContent || "")).toLowerCase();
                return t.includes("ajustes") || t.includes("settings");
            });
            return byAria || null;
        };

        const findAnchorHost = () => {
            // Try to locate the existing filter buttons container by using known buttons (Diarios/Contactos/Libro Mayor/etc.)
            const keywords = ["diarios", "contactos", "caja mayor", "libro mayor", "asientos", "asientos registrados", "comparación", "moneda", "en $"];
            const btn = Array.from(document.querySelectorAll("button, a")).find((el) => {
                const t = (el.textContent || "").toLowerCase().trim();
                if (!t) return false;
                return keywords.some((k) => t.includes(k));
            });
            if (btn) {
                return btn.closest(".o_control_panel")?.querySelector(".o_cp_bottom") || btn.parentElement || btn.closest(".o_control_panel") || null;
            }
            return null;
        };


        // ------------------------------------------------------------
        // UI builders
        // ------------------------------------------------------------
        const expenseTypeText = (value) => {
            if (value === "misc") return "Solo Gastos Varios";
            if (value === "vendor_bill") return "Facturas de Proveedor";
            return "Todos";
        };

        const buildDropdown = ({ key, icon, labelPrefix, items, currentValue, disabled, onSelect }) => {
            const group = document.createElement("div");
            group.className = "btn-group o_prs_expense_filter_group";
            group.setAttribute("data-prs-key", key);

            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "btn btn-secondary";
            btn.setAttribute("data-bs-toggle", "dropdown");
            btn.setAttribute("aria-expanded", "false");
            if (disabled) {
                btn.disabled = true;
                btn.classList.add("disabled");
            }

            const i = document.createElement("i");
            i.className = `fa ${icon} me-1`;
            btn.appendChild(i);

            const span = document.createElement("span");
            span.className = "o_prs_filter_label";
            span.textContent = `${labelPrefix}: ${items.find((x) => x.value === currentValue)?.label || items[0]?.label || ""}`;
            btn.appendChild(span);

            // caret
            const caret = document.createElement("i");
            caret.className = "fa fa-caret-down ms-2";
            btn.appendChild(caret);

            const menu = document.createElement("ul");
            menu.className = "dropdown-menu";

            for (const it of items) {
                const li = document.createElement("li");
                const a = document.createElement("a");
                a.href = "#";
                a.className = "dropdown-item" + (it.value === currentValue ? " active" : "");
                a.textContent = it.label;
                a.addEventListener("click", (ev) => {
                    ev.preventDefault();
                    ev.stopPropagation();
                    onSelect(it.value);
                });
                li.appendChild(a);
                menu.appendChild(li);
            }

            group.appendChild(btn);
            group.appendChild(menu);

            // Store pointers for later sync
            group.__prsBtn = btn;
            group.__prsLabel = span;
            group.__prsItems = items;
            group.__prsLabelPrefix = labelPrefix;

            return group;
        };

        const syncDropdownLabel = (group, value) => {
            if (!group || !group.__prsLabel) return;
            const label = group.__prsItems?.find((x) => x.value === value)?.label || group.__prsItems?.[0]?.label || "";
            group.__prsLabel.textContent = `${group.__prsLabelPrefix}: ${label}`;
            // Update active state
            const links = Array.from(group.querySelectorAll("a.dropdown-item"));
            for (const l of links) {
                l.classList.toggle("active", (l.textContent || "") === label);
            }
        };

        const buildOrUpdateUI = (options) => {
            const showType = !!options?.prs_filter_expense_type_enabled;
            const showPM = !!options?.prs_filter_payment_method_line_enabled;

            const host = findTopbarHost();
            if (!host) return;

            // Remove if disabled
            if (!showType && !showPM) {
                host.querySelectorAll(".o_prs_expense_topbar_filters").forEach((e) => e.remove());
                return;
            }

            // Create container once
            let container = host.querySelector(".o_prs_expense_topbar_filters");
            if (!container) {
                container = document.createElement("div");
                container.className = "o_prs_expense_topbar_filters d-flex flex-wrap gap-2 align-items-center";

                // Insert before settings gear if possible, otherwise append.
                const settingsBtn = findSettingsButton(host);
                if (settingsBtn && settingsBtn.parentElement) {
                    settingsBtn.parentElement.insertBefore(container, settingsBtn);
                } else {
                    host.appendChild(container);
                }
            }

            // Ensure groups exist / removed based on toggles
            const existingType = container.querySelector(".o_prs_expense_filter_group[data-prs-key='expense_type']");
            const existingPM = container.querySelector(".o_prs_expense_filter_group[data-prs-key='payment_method']");

            if (showType && !existingType) {
                const current = (options?.prs_expense_type) || (options?.prs_only_misc_expense ? "misc" : "all");
                const items = [
                    { value: "all", label: "Todos" },
                    { value: "misc", label: "Solo Gastos Varios" },
                    { value: "vendor_bill", label: "Facturas de Proveedor" },
                ];
                const dd = buildDropdown({
                    key: "expense_type",
                    icon: "fa-tag",
                    labelPrefix: "Tipo gasto",
                    items,
                    currentValue: items.some((x) => x.value === current) ? current : "all",
                    disabled: !options,
                    onSelect: async (v) => {
                        if (!options) return;
                        options.prs_expense_type = v || "all";
                        options.prs_only_misc_expense = v === "misc";
                        await triggerRefresh();
                    },
                });
                container.appendChild(dd);
            }
            if (!showType && existingType) existingType.remove();

            if (showPM && !existingPM) {
                const pmLines = Array.isArray(options?.prs_payment_method_lines) ? options.prs_payment_method_lines : [];
                const items = [{ value: "", label: "Todos" }, ...pmLines.map((x) => ({ value: String(x.id), label: x.name || String(x.id) }))];

                const currentId =
                    (Array.isArray(options?.prs_payment_method_line_ids) && options.prs_payment_method_line_ids.length ? options.prs_payment_method_line_ids[0] : null) ||
                    options?.prs_payment_method_line_id ||
                    null;

                const dd = buildDropdown({
                    key: "payment_method",
                    icon: "fa-credit-card",
                    labelPrefix: "Método pago",
                    items,
                    currentValue: currentId ? String(currentId) : "",
                    disabled: pmLines.length === 0,
                    onSelect: async (v) => {
                        if (!v) {
                            options.prs_payment_method_line_id = false;
                            options.prs_payment_method_line_ids = [];
                        } else {
                            const id = parseInt(v, 10);
                            options.prs_payment_method_line_id = id;
                            options.prs_payment_method_line_ids = [id];
                        }
                        await triggerRefresh();
                    },
                });
                container.appendChild(dd);
            }
            if (!showPM && existingPM) existingPM.remove();

            // Sync labels (especially after journals selection changes)
            const typeGroup = container.querySelector(".o_prs_expense_filter_group[data-prs-key='expense_type']");
            if (typeGroup) {
                const v = (options?.prs_expense_type) || (options?.prs_only_misc_expense ? "misc" : "all");
                syncDropdownLabel(typeGroup, ["all", "misc", "vendor_bill"].includes(v) ? v : "all");
            }

            const pmGroup = container.querySelector(".o_prs_expense_filter_group[data-prs-key='payment_method']");
            if (pmGroup) {
                const pmLines = Array.isArray(options?.prs_payment_method_lines) ? options.prs_payment_method_lines : [];
                const currentId =
                    (Array.isArray(options?.prs_payment_method_line_ids) && options.prs_payment_method_line_ids.length ? options.prs_payment_method_line_ids[0] : null) ||
                    options?.prs_payment_method_line_id ||
                    null;

                // Rebuild items if list changed
                const desiredItems = [{ value: "", label: "Todos" }, ...pmLines.map((x) => ({ value: String(x.id), label: x.name || String(x.id) }))];
                const currentItems = pmGroup.__prsItems || [];
                const same =
                    currentItems.length === desiredItems.length &&
                    currentItems.every((a, idx) => a.value === desiredItems[idx].value && a.label === desiredItems[idx].label);

                if (!same) {
                    // Replace dropdown entirely to keep bootstrap menu consistent
                    pmGroup.replaceWith(
                        buildDropdown({
                            key: "payment_method",
                            icon: "fa-credit-card",
                            labelPrefix: "Método pago",
                            items: desiredItems,
                            currentValue: currentId ? String(currentId) : "",
                            disabled: pmLines.length === 0,
                            onSelect: async (v) => {
                                if (!v) {
                                    options.prs_payment_method_line_id = false;
                                    options.prs_payment_method_line_ids = [];
                                } else {
                                    const id = parseInt(v, 10);
                                    options.prs_payment_method_line_id = id;
                                    options.prs_payment_method_line_ids = [id];
                                }
                                await triggerRefresh();
                            },
                        })
                    );
                } else {
                    syncDropdownLabel(pmGroup, currentId ? String(currentId) : "");
                    // enable/disable
                    const btn = pmGroup.__prsBtn;
                    if (btn) btn.disabled = pmLines.length === 0;
                }
            }
        };

        // ------------------------------------------------------------
        // Main loop
        // ------------------------------------------------------------
        const tick = () => {
            try {
                const options = getLiveOptions();
                if (!options) return;
                if (!isExpenseReportContext(options)) return;
                buildOrUpdateUI(options);
            } catch (_e) {
                // Never break the UI
            }
        };

        tick();
        const mo = new MutationObserver(() => tick());
        mo.observe(document.body, { childList: true, subtree: true });

        return {
            destroy() {
                mo.disconnect();
            },
        };
    },
});
