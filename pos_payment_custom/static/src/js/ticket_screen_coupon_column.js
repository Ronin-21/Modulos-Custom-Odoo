/* @odoo-module */

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted, onPatched } from "@odoo/owl";

const TAG = "[pos_payment_custom][ticket_coupon]";
const DEBUG = false;

function dlog(...args) {
  if (DEBUG) console.log(TAG, ...args);
}

function norm(s) {
  return String(s || "")
    .trim()
    .toLowerCase();
}

function extractRef(s) {
  // "Orden 00018-014-0001" -> "00018-014-0001"
  const t = String(s || "").trim();
  const m = t.match(/(\d{3,}-\d{2,}-\d{3,})/);
  return m && m[1] ? m[1] : "";
}

function getOrm(screen) {
  return screen.env?.services?.orm || null;
}

/**
 * Devuelve array de records para un "modelo" POS en Odoo 18:
 * - model.records (normal)
 * - array directo (fallback)
 */
function getModelRecords(pos, modelName) {
  const model = pos?.models?.[modelName];
  if (!model) return [];
  if (Array.isArray(model.records)) return model.records;
  if (Array.isArray(model)) return model;
  return [];
}

/** Encuentra el contenedor correcto (hay builds con más de un .orders) */
function findOrdersRoot() {
  const roots = Array.from(document.querySelectorAll(".orders"));
  for (const r of roots) {
    if (r.querySelector(".header-row") && r.querySelector(".order-row"))
      return r;
  }
  return document.querySelector(".orders") || null;
}

function getHeaderRow(root) {
  return root?.querySelector(".header-row") || null;
}

function getHeaderCols(headerRow) {
  return Array.from(headerRow?.children || []).filter((el) =>
    el.classList?.contains("col")
  );
}

function getOrderRows(root) {
  return Array.from(root?.querySelectorAll(".order-row") || []);
}

function ensureCouponHeaderCell(headerRow) {
  const cols = getHeaderCols(headerRow);
  const texts = cols.map((c) => norm(c.textContent));

  // Ya existe
  const existingIdx = texts.findIndex((t) => t === "cupón" || t === "cupon");
  if (existingIdx >= 0) {
    const receiptIdx =
      texts.indexOf("número de recibo") >= 0
        ? texts.indexOf("número de recibo")
        : texts.indexOf("numero de recibo") >= 0
        ? texts.indexOf("numero de recibo")
        : 1;
    return { insertIdx: existingIdx, receiptIdx };
  }

  const receiptIdx =
    texts.indexOf("número de recibo") >= 0
      ? texts.indexOf("número de recibo")
      : texts.indexOf("numero de recibo") >= 0
      ? texts.indexOf("numero de recibo")
      : 1;

  const totalIdx = texts.indexOf("total");
  const estadoIdx = texts.indexOf("estado");

  let insertIdx = totalIdx >= 0 ? totalIdx + 1 : cols.length;
  if (totalIdx < 0 && estadoIdx >= 0) insertIdx = estadoIdx;

  const deleteIdx = cols.findIndex((c) => c.getAttribute("name") === "delete");
  if (deleteIdx >= 0 && insertIdx > deleteIdx) insertIdx = deleteIdx;

  const cell = document.createElement("div");
  cell.className = "col narrow p-2 o_pos_coupon_header";
  cell.textContent = "Cupón";
  cell.style.whiteSpace = "nowrap";
  cell.style.textAlign = "right";

  if (insertIdx >= cols.length) headerRow.appendChild(cell);
  else headerRow.insertBefore(cell, cols[insertIdx]);

  return { insertIdx, receiptIdx };
}

function getVisibleRefs(root, receiptIdx) {
  const refs = [];
  for (const row of getOrderRows(root)) {
    const cols = Array.from(row.children || []).filter((el) =>
      el.classList?.contains("col")
    );
    const receiptCell = cols[receiptIdx] || null;
    const ref = extractRef(receiptCell?.textContent || "");
    if (ref) refs.push(ref);
  }
  return Array.from(new Set(refs));
}

function buildOrDomain(refs) {
  const conds = refs.map((r) => ["pos_reference", "ilike", r]);
  if (!conds.length) return [];
  if (conds.length === 1) return conds[0];
  return Array(conds.length - 1)
    .fill("|")
    .concat(conds);
}

/**
 * Fetch de cupones:
 * 1) Preferimos cache local del POS (sin RPC)
 * 2) Si faltan, intentamos orm.searchRead (puede fallar por permisos)
 */
async function fetchCoupons(screen, refs) {
  const pos = screen.pos || screen.env?.services?.pos;
  const result = [];

  // 1) Cache local
  const orders = getModelRecords(pos, "pos.order");
  if (orders.length) {
    const idx = new Map();
    for (const o of orders) {
      const r = extractRef(o.pos_reference || "");
      if (r && !idx.has(r)) idx.set(r, o);
    }

    for (const ref of refs) {
      const o = idx.get(ref);
      if (o) {
        result.push({
          pos_reference: o.pos_reference,
          coupon_numbers: o.coupon_numbers || "",
        });
      }
    }
  }

  dlog("Del cache local:", result.length, "de", refs.length);

  if (result.length === refs.length) return result;

  // 2) Fallback: RPC estándar
  const orm = getOrm(screen);
  const foundRefs = new Set(result.map((r) => extractRef(r.pos_reference)));
  const missing = refs.filter((r) => !foundRefs.has(r));
  if (!missing.length) return result;

  if (!orm) {
    for (const ref of missing)
      result.push({ pos_reference: ref, coupon_numbers: "" });
    return result;
  }

  const domain = buildOrDomain(missing);
  if (!domain.length) return result;

  try {
    dlog("Haciendo searchRead para faltantes:", missing.length);
    const serverResult = await orm.searchRead(
      "pos.order",
      domain,
      ["pos_reference", "coupon_numbers"],
      { limit: 200 }
    );
    dlog("Del servidor:", serverResult?.length || 0);
    return result.concat(serverResult || []);
  } catch (e) {
    console.warn(TAG, "RPC searchRead falló (no crítico):", e?.message || e);
    for (const ref of missing)
      result.push({ pos_reference: ref, coupon_numbers: "" });
    return result;
  }
}

function ensureCouponCells(root, insertIdx, receiptIdx, couponCache) {
  for (const row of getOrderRows(root)) {
    const cols = Array.from(row.children || []).filter((el) =>
      el.classList?.contains("col")
    );

    let cell = row.querySelector(".o_pos_coupon_cell");
    if (!cell) {
      cell = document.createElement("div");
      cell.className = "col narrow p-2 o_pos_coupon_cell";
      cell.style.whiteSpace = "nowrap";
      cell.style.textAlign = "right";
      cell.style.fontSize = "12px";

      const deleteIdx = cols.findIndex(
        (c) => c.getAttribute("name") === "delete"
      );
      let idx = insertIdx;
      if (deleteIdx >= 0 && idx > deleteIdx) idx = deleteIdx;

      if (idx >= cols.length) row.appendChild(cell);
      else row.insertBefore(cell, cols[idx]);
    }

    const currentCols = Array.from(row.children || []).filter((el) =>
      el.classList?.contains("col")
    );
    const receiptCell = currentCols[receiptIdx] || null;
    const ref = extractRef(receiptCell?.textContent || "");

    const value = ref ? couponCache.get(ref) || "" : "";
    cell.textContent = value || "-";
    cell.style.opacity = value ? "1" : "0.3";
    cell.style.color = value ? "inherit" : "#999";
  }
}

/**
 * ✅ Filtrado DOM por texto completo de la fila.
 * Como Cupón ya está en la fila, con esto el buscador “incluye” cupón automáticamente.
 * Importante: NO toca la lógica core, solo oculta/mostrar rows visibles.
 */
function applyDomSearchFilter(root, query) {
  const q = norm(query);
  const rows = getOrderRows(root);

  for (const row of rows) {
    // Restaurar si estaba oculto por nuestro filtro anterior
    if (row.dataset?.couponDomHidden === "1") {
      row.style.display = "";
      delete row.dataset.couponDomHidden;
    }
    if (!q) continue;

    const haystack = norm(row.textContent);
    const show = haystack.includes(q);

    if (!show) {
      row.style.display = "none";
      row.dataset.couponDomHidden = "1";
    }
  }
}

/**
 * ✅ Dropdown del buscador: inyecta "Número de cupón: <query>"
 * sin tocar templates del core.
 */
function findSearchDropdown() {
  const candidates = Array.from(
    document.querySelectorAll(
      ".dropdown-menu, .o-autocomplete, .o_searchbar_autocomplete, .search-bar .dropdown-menu"
    )
  );
  for (const el of candidates) {
    const t = norm(el.textContent);
    // el menú real suele contener estos labels
    if (t.includes("número de orden") && t.includes("cliente")) return el;
  }
  return null;
}

function ensureCouponDropdownItem(menu, query) {
  if (!menu) return;

  // borrar el item anterior
  const prev = menu.querySelector(".o_pos_coupon_search_item");
  if (prev) prev.remove();

  const q = String(query || "").trim();
  if (!q) return;

  // intentar copiar clases de un item existente
  const sample = menu.querySelector("div, li, a");
  const item = document.createElement(sample?.tagName === "A" ? "a" : "div");

  item.className =
    (sample?.className || "dropdown-item") + " o_pos_coupon_search_item";
  item.style.cursor = "pointer";
  item.style.whiteSpace = "nowrap";

  // Texto visible
  item.textContent = `Número de cupón: ${q}`;

  // Insertarlo arriba (después del primero) para que se vea rápido
  const first = menu.firstElementChild;
  if (first && first.nextSibling) menu.insertBefore(item, first.nextSibling);
  else menu.appendChild(item);
}

/** Busca input de búsqueda del TicketScreen (robusto) */
function findTicketSearchInput(root) {
  const selectors = [
    ".search-bar input",
    ".searchbox input",
    ".search input",
    "input[placeholder*='Buscar']",
    "input[placeholder*='Search']",
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && el.tagName === "INPUT") return el;
  }
  const screenEl =
    root?.closest(".screen") || root?.closest(".pos-content") || null;
  const fallback = screenEl?.querySelector("input") || null;
  return fallback && fallback.tagName === "INPUT" ? fallback : null;
}

async function apply(screen) {
  try {
    const root = findOrdersRoot();
    if (!root) return;

    const headerRow = getHeaderRow(root);
    if (!headerRow) return;

    const { insertIdx, receiptIdx } = ensureCouponHeaderCell(headerRow);

    screen.__couponCache = screen.__couponCache || new Map();
    screen.__couponLoading = screen.__couponLoading || false;

    if (!screen.__ticketSearchInput) {
      screen.__ticketSearchInput = findTicketSearchInput(root);
    }
    const query = screen.__ticketSearchInput?.value || "";

    // Pintar lo que ya tenemos
    ensureCouponCells(root, insertIdx, receiptIdx, screen.__couponCache);

    // ✅ Mejorar dropdown del buscador
    ensureCouponDropdownItem(findSearchDropdown(), query);

    // ✅ Aplicar filtro DOM (incluye cupón)
    applyDomSearchFilter(root, query);

    const refs = getVisibleRefs(root, receiptIdx);
    const missing = refs.filter((r) => !screen.__couponCache.has(r));
    if (!missing.length || screen.__couponLoading) return;

    screen.__couponLoading = true;
    try {
      const rows = await fetchCoupons(screen, missing);

      for (const rec of rows) {
        const ref = extractRef(rec.pos_reference || "");
        if (ref) screen.__couponCache.set(ref, rec.coupon_numbers || "");
      }
      for (const r of missing) {
        if (!screen.__couponCache.has(r)) screen.__couponCache.set(r, "");
      }

      ensureCouponCells(root, insertIdx, receiptIdx, screen.__couponCache);

      // ✅ Replicar dropdown + filtro (por si ahora aparece cupón)
      ensureCouponDropdownItem(findSearchDropdown(), query);
      applyDomSearchFilter(root, query);

      dlog(
        "Refs visibles:",
        refs.length,
        "missing:",
        missing.length,
        "rows:",
        rows.length
      );
    } finally {
      screen.__couponLoading = false;
    }
  } catch (e) {
    console.error(TAG, "Error en apply:", e);
  }
}

/** Debounce global */
let globalObserver = null;
let lastRoot = null;
let timer = null;
function scheduleApply(screen, delay = 120) {
  clearTimeout(timer);
  timer = setTimeout(() => apply(screen), delay);
}

function attachSearchListener(screen) {
  const root = findOrdersRoot();
  if (!root) return;

  if (!screen.__ticketSearchInput) {
    screen.__ticketSearchInput = findTicketSearchInput(root);
  }
  const input = screen.__ticketSearchInput;
  if (!input) return;

  if (input.dataset?.couponSearchListener === "1") return;
  input.dataset.couponSearchListener = "1";

  input.addEventListener(
    "input",
    () => {
      scheduleApply(screen, 40);
    },
    { passive: true }
  );
}

patch(TicketScreen.prototype, {
  setup() {
    super.setup();

    onMounted(() => {
      scheduleApply(this, 150);
      attachSearchListener(this);

      const root = findOrdersRoot();
      if (root && root !== lastRoot) {
        lastRoot = root;
        if (globalObserver) globalObserver.disconnect();

        globalObserver = new MutationObserver(() => scheduleApply(this, 120));
        globalObserver.observe(root, { childList: true, subtree: true });
        dlog("MutationObserver activo (root nuevo)");
      }
    });

    onPatched(() => {
      attachSearchListener(this);
      scheduleApply(this, 80);

      const root = findOrdersRoot();
      if (root && root !== lastRoot) {
        lastRoot = root;
        if (globalObserver) globalObserver.disconnect();

        globalObserver = new MutationObserver(() => scheduleApply(this, 120));
        globalObserver.observe(root, { childList: true, subtree: true });
        dlog("MutationObserver reenganche (root nuevo)");
      }
    });
  },
});
