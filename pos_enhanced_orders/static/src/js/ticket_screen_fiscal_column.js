/* @odoo-module */

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted, onPatched } from "@odoo/owl";

const TAG = "[pos_fiscal_info][ticket_fiscal]";
const DEBUG = false;

function dlog(...args) {
  if (DEBUG) console.log(TAG, ...args);
}

const fiscalRpcCache = new Map();

function extractRef(s) {
  const t = String(s || "").trim();
  const m = t.match(/(\d{3,}-\d{2,}-\d{3,})/);
  return m && m[1] ? m[1] : "";
}

function getModelRecords(pos, modelName) {
  const model = pos?.models?.[modelName];
  if (!model) return [];
  if (Array.isArray(model.records)) return model.records;
  if (Array.isArray(model)) return model;
  return [];
}

function findOrdersRoot() {
  const roots = Array.from(document.querySelectorAll(".orders"));
  for (const r of roots) {
    if (r.querySelector(".header-row") && r.querySelector(".order-row"))
      return r;
  }
  return document.querySelector(".orders") || null;
}

function getOrderRows(root) {
  return Array.from(root?.querySelectorAll(".order-row") || []);
}

function findOrderNumberColumn(row) {
  const cols = Array.from(row.children || []).filter((el) =>
    el.classList?.contains("col"),
  );

  for (let i = 0; i < Math.min(cols.length, 4); i++) {
    const text = cols[i]?.textContent || "";
    if (text.toLowerCase().includes("orden") && extractRef(text))
      return cols[i];
  }
  return cols[1] || null;
}

function buildFiscalCache(screen) {
  const pos = screen.pos || screen.env?.services?.pos;
  const cache = new Map();

  const orders = getModelRecords(pos, "pos.order");
  for (const order of orders) {
    const ref = extractRef(order.pos_reference || "");
    if (!ref) continue;

    const invoice_name = order.invoice_name || "";
    const is_fiscal = order.is_fiscal === true || !!invoice_name;

    cache.set(ref, { invoice_name, is_fiscal });
  }
  return cache;
}

function collectRefsFromDOM(root) {
  const refs = [];
  for (const row of getOrderRows(root)) {
    const orderCol = findOrderNumberColumn(row);
    if (!orderCol) continue;
    const txt = (
      orderCol.dataset.posOriginalText ||
      orderCol.textContent ||
      ""
    ).trim();
    const ref = extractRef(txt);
    if (ref) refs.push(ref);
  }
  return Array.from(new Set(refs));
}

async function fetchFiscalInfoFromServer(screen, refs) {
  const env = screen.env || {};
  const orm =
    env.services?.orm ||
    env.services?.pos?.orm ||
    screen.orm ||
    screen.pos?.orm;
  const result = new Map();

  if (!orm || !refs?.length) return result;

  const unique = Array.from(new Set(refs)).filter(Boolean);

  for (const r of unique) {
    if (fiscalRpcCache.has(r)) {
      result.set(r, fiscalRpcCache.get(r));
    }
  }

  const toFetch = unique.filter((r) => !fiscalRpcCache.has(r));
  if (!toFetch.length) return result;

  const es = toFetch.map((r) => `Orden ${r}`);
  const en = toFetch.map((r) => `Order ${r}`);
  const domain = [
    "|",
    ["pos_reference", "in", es],
    ["pos_reference", "in", en],
  ];

  try {
    const rows = await orm.searchRead(
      "pos.order",
      domain,
      ["pos_reference", "invoice_name", "is_fiscal", "account_move"],
      { limit: toFetch.length },
    );

    for (const row of rows || []) {
      const ref = extractRef(row.pos_reference || "");
      if (!ref) continue;

      const m2o = row.account_move;
      const m2oName = Array.isArray(m2o) ? m2o[1] || "" : "";
      const invoice_name = row.invoice_name || m2oName || "";
      const is_fiscal = row.is_fiscal === true || !!invoice_name;

      const payload = { invoice_name, is_fiscal };
      fiscalRpcCache.set(ref, payload);
      result.set(ref, payload);
    }

    for (const ref of toFetch) {
      if (!result.has(ref)) {
        const payload = {
          invoice_name: "",
          is_fiscal: false,
          _not_found: true,
        };
        fiscalRpcCache.set(ref, payload);
        result.set(ref, payload);
      }
    }

    return result;
  } catch (e) {
    console.warn(TAG, "⚠️ No se pudo leer info fiscal por RPC:", e);

    for (const ref of toFetch) {
      if (!fiscalRpcCache.has(ref)) {
        const payload = {
          invoice_name: "",
          is_fiscal: false,
          _rpc_error: true,
        };
        fiscalRpcCache.set(ref, payload);
        result.set(ref, payload);
      }
    }

    return result;
  }
}

function applyFiscalInfo(root, fiscalCache) {
  for (const row of getOrderRows(root)) {
    const orderCol = findOrderNumberColumn(row);
    if (!orderCol) continue;

    const currentText = (
      orderCol.dataset.posOriginalText ||
      orderCol.textContent ||
      ""
    ).trim();
    if (!orderCol.dataset.posOriginalText)
      orderCol.dataset.posOriginalText = currentText;

    const ref = extractRef(currentText);
    if (!ref) continue;

    const fiscalInfo = fiscalCache.get(ref);
    const invoice_name = fiscalInfo?.invoice_name || "";
    const is_fiscal = fiscalInfo?.is_fiscal || false;

    // ✅ Usar clases en lugar de estilos inline
    orderCol.innerHTML = "";
    orderCol.classList.add("pos-col-receipt");

    const orderSpan = document.createElement("span");
    orderSpan.className = "order-number";
    orderSpan.textContent = currentText;
    orderCol.appendChild(orderSpan);

    const badge = document.createElement("span");
    // ✅ SOLO clases, sin estilos inline
    badge.className = is_fiscal
      ? "pos-fiscal-badge pos-fiscal-badge--facturado"
      : "pos-fiscal-badge pos-fiscal-badge--sin-factura";

    badge.textContent = invoice_name || "Orden POS";
    orderCol.appendChild(badge);
  }
}

let timer = null;

function scheduleApply(screen, delay = 120) {
  clearTimeout(timer);
  timer = setTimeout(() => apply(screen), delay);
}

async function apply(screen) {
  if (screen.__fiscalApplying) return;
  screen.__fiscalApplying = true;

  try {
    const pos = screen.pos || screen.env?.services?.pos;
    const cfg = pos?.config || {};

    if (cfg.show_ticket_col_receipt === false) {
      return;
    }

    if (cfg.show_ticket_receipt_fiscal_info === false) {
      return;
    }

    const root = findOrdersRoot();
    if (!root) return;

    const cache = buildFiscalCache(screen);
    const refs = collectRefsFromDOM(root);
    const fetched = await fetchFiscalInfoFromServer(screen, refs);

    for (const [ref, payload] of fetched.entries()) {
      cache.set(ref, payload);
    }

    applyFiscalInfo(root, cache);
  } catch (e) {
    console.error(TAG, "❌ Error en apply:", e);
  } finally {
    screen.__fiscalApplying = false;
  }
}

patch(TicketScreen.prototype, {
  setup() {
    super.setup();

    onMounted(() => {
      scheduleApply(this, 150);
    });

    onPatched(() => {
      scheduleApply(this, 80);
    });
  },
});
