/* @odoo-module */

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted, onPatched } from "@odoo/owl";

const paymentCache = new Map();
let timer = null;

function schedule(screen, delay = 120) {
  clearTimeout(timer);
  timer = setTimeout(() => apply(screen), delay);
}

function getPos(screen) {
  return screen.pos || screen.env?.services?.pos;
}

function findOrdersRoot() {
  const roots = Array.from(document.querySelectorAll(".orders"));
  for (const r of roots) {
    if (r.querySelector(".header-row") && r.querySelector(".order-row"))
      return r;
  }
  return document.querySelector(".orders") || null;
}

function extractRef(s) {
  const t = String(s || "").trim();
  const m = t.match(/(\d{3,}-\d{2,}-\d{3,})/);
  return m && m[1] ? m[1] : "";
}

function findReceiptColumn(row) {
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

function buildMapFromPos(pos) {
  const map = new Map();
  const model = pos?.models?.["pos.order"];
  const orders = model?.getAll?.() || model?.records || [];

  // ✅ SIEMPRE actualizar desde el modelo (no skipear por cache)
  for (const o of orders) {
    const ref = extractRef(o.pos_reference || "");
    if (!ref) continue;

    const val = (o.payment_method_names || "").trim();
    // ✅ Actualizar cache SIEMPRE (incluso si está vacío)
    map.set(ref, val);
    paymentCache.set(ref, val); // Actualizar cache global también
  }

  return map;
}

function ensurePaymentsColumn(root) {
  const headerRow = root?.querySelector(".header-row");
  if (!headerRow) return;

  let payHeader = headerRow.querySelector('[data-pos-payments-col="1"]');
  if (payHeader) return;

  const existsByText = Array.from(headerRow.children || []).some((el) =>
    /^pagos$/i.test((el.textContent || "").trim()),
  );
  if (existsByText) return;

  const sample = headerRow.children?.[0];
  const cls = sample?.className || "col";

  const h = document.createElement("div");
  h.className = cls;
  h.classList.add("pos-payments-header", "pos-col-payments", "pos-col-left");
  h.dataset.posPaymentsCol = "1";
  h.textContent = "Pagos";
  headerRow.appendChild(h);

  const rows = Array.from(root.querySelectorAll(".order-row") || []);
  for (const row of rows) {
    const existing = row.querySelector('[data-pos-payments-col="1"]');
    if (existing) continue;

    const c = document.createElement("div");
    c.className = cls;
    c.classList.add("pos-payments-cell", "pos-col-payments", "pos-col-left");
    c.dataset.posPaymentsCol = "1";
    row.appendChild(c);
  }
}

function ensurePaymentsCells(root) {
  const rows = Array.from(root.querySelectorAll(".order-row") || []);
  const headerRow = root?.querySelector(".header-row");
  const headerHasPayments = !!headerRow?.querySelector(
    '[data-pos-payments-col="1"]',
  );

  if (!headerHasPayments) return;

  const sample = headerRow?.children?.[0];
  const cls = sample?.className || "col";

  for (const row of rows) {
    const existing = row.querySelector('[data-pos-payments-col="1"]');
    if (existing) continue;

    const c = document.createElement("div");
    c.className = cls;
    c.classList.add("pos-payments-cell", "pos-col-payments", "pos-col-left");
    c.dataset.posPaymentsCol = "1";
    row.appendChild(c);
  }
}

async function apply(screen) {
  if (screen.__paymentsApplying) return;
  screen.__paymentsApplying = true;

  try {
    const pos = getPos(screen);
    const root = findOrdersRoot();
    if (!pos || !root) return;

    if (pos.config?.show_ticket_col_payments !== true) return;

    ensurePaymentsColumn(root);
    ensurePaymentsCells(root);

    // ✅ SIEMPRE actualizar desde modelo POS (actualiza cache automáticamente)
    const localMap = buildMapFromPos(pos);

    // Renderizar celdas
    const rows = Array.from(root.querySelectorAll(".order-row") || []);
    for (const row of rows) {
      const receiptCol = findReceiptColumn(row);
      const ref = extractRef(receiptCol?.textContent || "");
      if (!ref) continue;

      const cell = row.querySelector('[data-pos-payments-col="1"]');
      if (!cell) continue;

      const val = (localMap.get(ref) || "").trim();
      const newText = val || "-";

      if (cell.textContent !== newText) {
        cell.textContent = newText;
        cell.title = val || "";
      }
    }
  } finally {
    screen.__paymentsApplying = false;
  }
}

patch(TicketScreen.prototype, {
  setup() {
    super.setup();
    onMounted(() => schedule(this, 150));
    onPatched(() => schedule(this, 80));
  },
});
