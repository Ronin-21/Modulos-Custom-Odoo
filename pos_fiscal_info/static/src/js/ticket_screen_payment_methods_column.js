/* @odoo-module */

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted, onPatched } from "@odoo/owl";

const paymentCache = new Map(); // ref -> string ("" cache negativo)
let timer = null;

function schedule(screen, delay = 120) {
  clearTimeout(timer);
  timer = setTimeout(() => apply(screen), delay);
}

function getPos(screen) {
  return screen.pos || screen.env?.services?.pos;
}
function getOrm(screen) {
  const env = screen.env || {};
  return (
    env.services?.orm || env.services?.pos?.orm || screen.orm || screen.pos?.orm
  );
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
  const orders = Array.isArray(model?.records) ? model.records : [];
  for (const o of orders) {
    const ref = extractRef(o.pos_reference || "");
    if (!ref) continue;
    const val = (o.payment_method_names || "").trim();
    if (val) map.set(ref, val);
  }
  return map;
}

function ensurePaymentsColumn(root) {
  const headerRow = root?.querySelector(".header-row");
  if (!headerRow) return;

  const exists = Array.from(headerRow.children || []).some((el) =>
    /pagos|m[ée]todos de pago/i.test((el.textContent || "").trim()),
  );
  if (exists) return;

  const sample = headerRow.children?.[0];
  const cls = sample?.className || "col";

  const h = document.createElement("div");
  h.className = cls;
  h.classList.add("pos-payments-header");
  h.textContent = "Pagos";
  headerRow.appendChild(h);

  const rows = Array.from(root.querySelectorAll(".order-row") || []);
  for (const row of rows) {
    const c = document.createElement("div");
    c.className = cls;
    c.classList.add("pos-payments-cell");
    c.dataset.posPaymentsCol = "1";
    row.appendChild(c);
  }
}

function ensurePaymentsCells(root) {
  const headerRow = root?.querySelector(".header-row");
  if (!headerRow) return;

  const headerCount = headerRow.children?.length || 0;
  const rows = Array.from(root.querySelectorAll(".order-row") || []);

  for (const row of rows) {
    while ((row.children?.length || 0) < headerCount) {
      const sample = row.children?.[0];
      const cls = sample?.className || "col";
      const c = document.createElement("div");
      c.className = cls;
      c.classList.add("pos-payments-cell");
      c.dataset.posPaymentsCol = "1";
      row.appendChild(c);
    }
  }
}

function getPaymentsColumnIndex(root) {
  const headerRow = root?.querySelector(".header-row");
  if (!headerRow) return -1;
  const children = Array.from(headerRow.children || []);
  for (let i = 0; i < children.length; i++) {
    const t = (children[i]?.textContent || "").trim();
    if (/pagos|m[ée]todos de pago/i.test(t)) return i;
  }
  return -1;
}

async function fetchMissing(screen, refs) {
  const orm = getOrm(screen);
  if (!orm) return;

  const unique = Array.from(new Set(refs)).filter(Boolean);
  const toFetch = unique.filter((r) => !paymentCache.has(r));
  if (!toFetch.length) return;

  const es = toFetch.map((r) => `Orden ${r}`);
  const en = toFetch.map((r) => `Order ${r}`);
  const domain = [
    "|",
    ["pos_reference", "in", es],
    ["pos_reference", "in", en],
  ];

  const rows = await orm.searchRead(
    "pos.order",
    domain,
    ["pos_reference", "payment_method_names"],
    { limit: toFetch.length },
  );

  for (const row of rows || []) {
    const ref = extractRef(row.pos_reference || "");
    if (!ref) continue;
    paymentCache.set(ref, (row.payment_method_names || "").trim());
  }
  // cache negativo
  for (const r of toFetch) {
    if (!paymentCache.has(r)) paymentCache.set(r, "");
  }
}

async function apply(screen) {
  if (screen.__paymentsApplying) return;
  screen.__paymentsApplying = true;

  try {
    const pos = getPos(screen);
    const root = findOrdersRoot();
    if (!pos || !root) return;

    // Solo si el check está activo
    if (pos.config?.show_ticket_col_payments !== true) return;

    ensurePaymentsColumn(root);
    ensurePaymentsCells(root);

    const idx = getPaymentsColumnIndex(root);
    if (idx < 0) return;

    const localMap = buildMapFromPos(pos);

    const rows = Array.from(root.querySelectorAll(".order-row") || []);
    const refs = [];
    for (const row of rows) {
      const receiptCol = findReceiptColumn(row);
      const ref = extractRef(receiptCol?.textContent || "");
      if (ref) refs.push(ref);
    }

    const missing = refs.filter(
      (r) => !localMap.get(r) && !paymentCache.has(r),
    );
    if (missing.length) {
      try {
        await fetchMissing(screen, missing);
      } catch (e) {
        for (const r of missing)
          if (!paymentCache.has(r)) paymentCache.set(r, "");
      }
    }

    // Pintar sin provocar mutaciones innecesarias
    for (const row of rows) {
      const receiptCol = findReceiptColumn(row);
      const ref = extractRef(receiptCol?.textContent || "");
      if (!ref) continue;

      const val = (localMap.get(ref) || paymentCache.get(ref) || "").trim();
      const cell = row.children?.[idx];
      if (!cell) continue;

      const newText = val || "-";
      if (cell.textContent !== newText) {
        cell.textContent = newText;
      }
      // Tooltip para ver el texto completo al pasar el mouse
      cell.title = (val || "").trim();
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
