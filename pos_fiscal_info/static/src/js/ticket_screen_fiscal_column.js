/* @odoo-module */

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted, onPatched, onWillUnmount } from "@odoo/owl";

const TAG = "[pos_fiscal_info][ticket_fiscal]";
const DEBUG = false; // ponelo en true si querés logs

function dlog(...args) {
  if (DEBUG) console.log(TAG, ...args);
}

// Cache RPC: ref (00461-004-0005) -> { invoice_name, is_fiscal }
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

  // Buscar columna que contenga "Orden XXXXX-XXX-XXXX"
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

  // 1) Primero devolver lo que ya tenemos en cache (clave del fix)
  for (const r of unique) {
    if (fiscalRpcCache.has(r)) {
      result.set(r, fiscalRpcCache.get(r));
    }
  }

  // 2) Solo pedir por RPC los que no están cacheados
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

    // 3) Cache negativo para refs no encontrados (evita loops y “parpadeos”)
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

    // Si falla RPC, igual cacheamos negativo para no repetir infinito
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

    orderCol.innerHTML = "";
    orderCol.style.display = "flex";
    orderCol.style.flexDirection = "column";
    orderCol.style.gap = "2px";
    orderCol.style.alignItems = "flex-start";

    const orderSpan = document.createElement("span");
    orderSpan.textContent = currentText;
    orderSpan.style.fontSize = "13px";
    orderSpan.style.fontWeight = "500";
    orderCol.appendChild(orderSpan);

    const badge = document.createElement("span");
    badge.className = is_fiscal
      ? "pos-fiscal-badge pos-fiscal-badge--facturado"
      : "pos-fiscal-badge pos-fiscal-badge--sin-factura";

    // ✅ Acá aparece el número de factura (FA-B 00006-00000875)
    badge.textContent = invoice_name || "Sin factura";

    badge.style.padding = "2px 6px";
    badge.style.borderRadius = "3px";
    badge.style.fontSize = "10px";
    badge.style.fontWeight = "600";
    badge.style.whiteSpace = "nowrap";
    badge.style.border = "1px solid";
    badge.style.display = "inline-block";
    badge.style.maxWidth = "100%";
    badge.style.overflow = "hidden";
    badge.style.textOverflow = "ellipsis";

    if (is_fiscal) {
      badge.style.backgroundColor = "#d4edda";
      badge.style.color = "#155724";
      badge.style.borderColor = "#c3e6cb";
    } else {
      badge.style.backgroundColor = "#fff3cd";
      badge.style.color = "#856404";
      badge.style.borderColor = "#ffeeba";
    }

    orderCol.appendChild(badge);
  }
}

let globalObserver = null;
let lastRoot = null;
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

    // Si está oculta la columna, no tiene sentido modificarla visualmente
    if (cfg.show_ticket_col_receipt === false) {
      return;
    }

    // Check para NO modificar "Número de recibo" (Factura / Sin factura)
    if (cfg.show_ticket_receipt_fiscal_info === false) {
      return;
    }

    const root = findOrdersRoot();
    if (!root) return;

    // Cache desde el POS (si vinieron los campos)
    const cache = buildFiscalCache(screen);

    // Refs visibles en DOM
    const refs = collectRefsFromDOM(root);

    // ✅ Pedimos info fiscal para refs visibles, pero:
    // - si ya está cacheado, NO hace RPC
    // - igual nos devuelve el cache para re-aplicar (evita que desaparezca)
    const fetched = await fetchFiscalInfoFromServer(screen, refs);

    // Merge: RPC/cache siempre tiene prioridad sobre lo local
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

      const root = findOrdersRoot();
      if (root && root !== lastRoot) {
        lastRoot = root;
        if (globalObserver) globalObserver.disconnect();

        globalObserver = new MutationObserver(() => scheduleApply(this, 120));
        globalObserver.observe(root, { childList: true, subtree: true });
      }
    });

    onPatched(() => {
      scheduleApply(this, 80);

      const root = findOrdersRoot();
      if (root && root !== lastRoot) {
        lastRoot = root;
        if (globalObserver) globalObserver.disconnect();

        globalObserver = new MutationObserver(() => scheduleApply(this, 120));
        globalObserver.observe(root, { childList: true, subtree: true });
      }
    });

    onWillUnmount(() => {
      if (globalObserver) {
        globalObserver.disconnect();
        globalObserver = null;
      }
      lastRoot = null;
    });
  },
});
