/* @odoo-module */

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted, onPatched, onWillUnmount } from "@odoo/owl";

const invoiceStateCache = new Map();
let timer = null;
let observer = null;
let observedRoot = null;
let isApplying = false;

const STATE_LABELS = {
  posted: "Confirmada",
  draft: "Borrador",
  cancel: "Cancelada",
  no_invoice: "Sin factura",
};

function schedule(screen, delay = 140) {
  clearTimeout(timer);
  timer = setTimeout(() => apply(screen), delay);
}

function getPos(screen) {
  return screen.pos || screen.env?.services?.pos;
}

function findOrdersRoot() {
  const roots = Array.from(document.querySelectorAll(".orders"));
  for (const r of roots) {
    if (r.querySelector(".header-row")) return r;
  }
  return document.querySelector(".orders") || null;
}

function ensureObserver(screen) {
  const root = findOrdersRoot();
  if (!root || observedRoot === root) return;

  if (observer) observer.disconnect();
  observedRoot = root;

  observer = new MutationObserver(() => {
    if (isApplying) return;
    schedule(screen, 120);
  });

  observer.observe(root, { childList: true, subtree: false });
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
  for (let i = 0; i < Math.min(cols.length, 5); i++) {
    const text = cols[i]?.textContent || "";
    if (text.toLowerCase().includes("orden") && extractRef(text))
      return cols[i];
  }
  return cols[1] || null;
}

function findHeaderByText(headerRow, regex) {
  const children = Array.from(headerRow.children || []);
  for (let i = 0; i < children.length; i++) {
    const t = (children[i]?.textContent || "").trim();
    if (regex.test(t)) return { el: children[i], idx: i };
  }
  return { el: null, idx: -1 };
}

function ensureInvoiceStateColumn(root) {
  const headerRow = root?.querySelector(".header-row");
  if (!headerRow) return;

  let invHeader = headerRow.querySelector('[data-pos-invoice-state-col="1"]');
  const payHeader =
    headerRow.querySelector('[data-pos-payments-col="1"]') ||
    findHeaderByText(headerRow, /pagos|m[ée]todos de pago/i).el;

  if (!invHeader) {
    const sample = headerRow.children?.[0];
    const cls = sample?.className || "col";

    invHeader = document.createElement("div");
    invHeader.className = cls;
    invHeader.classList.add("pos-col-invoice-state", "pos-col-center");
    invHeader.dataset.posInvoiceStateCol = "1";
    invHeader.textContent = "Estado factura";

    if (payHeader) headerRow.insertBefore(invHeader, payHeader);
    else headerRow.appendChild(invHeader);
  }

  const rows = Array.from(root.querySelectorAll(".order-row") || []);
  for (const row of rows) {
    let cell = row.querySelector('[data-pos-invoice-state-col="1"]');

    const payCell =
      row.querySelector('[data-pos-payments-col="1"]') ||
      row.querySelector(".pos-payments-cell");

    if (!cell) {
      const sample = row.children?.[0];
      const cls = sample?.className || "col";

      cell = document.createElement("div");
      cell.className = cls;
      cell.classList.add(
        "pos-invoice-state-cell",
        "pos-col-invoice-state",
        "pos-col-center",
      );
      cell.dataset.posInvoiceStateCol = "1";
      cell.textContent = "-";

      if (payCell) row.insertBefore(cell, payCell);
      else row.appendChild(cell);
    }
  }
}

function renderBadge(cell, info) {
  const state = (info?.state || "no_invoice").trim();
  const label = (info?.label || STATE_LABELS[state] || "Sin factura").trim();

  const existing = cell.querySelector("span[data-state]");
  if (
    existing &&
    existing.dataset.state === state &&
    existing.textContent === label
  ) {
    return; // Ya está renderizado correctamente
  }

  cell.innerHTML = "";

  const span = document.createElement("span");
  span.dataset.state = state;

  if (state === "posted") {
    span.className = "pos-invoice-state-badge pos-invoice-state-badge--posted";
  } else if (state === "draft") {
    span.className = "pos-invoice-state-badge pos-invoice-state-badge--draft";
  } else if (state === "cancel") {
    span.className = "pos-invoice-state-badge pos-invoice-state-badge--cancel";
  } else {
    span.className = "pos-invoice-state-badge pos-invoice-state-badge--none";
  }

  span.textContent = label;
  cell.appendChild(span);
  cell.title = label;
}

function apply(screen) {
  const pos = getPos(screen);
  const root = findOrdersRoot();
  if (!pos || !root) return;

  if (pos.config?.show_ticket_col_invoice_state !== true) return;

  if (isApplying) return;
  isApplying = true;

  try {
    ensureObserver(screen);
    ensureInvoiceStateColumn(root);

    const rows = Array.from(root.querySelectorAll(".order-row") || []);

    // ✅ SIEMPRE actualizar cache desde el modelo POS (sin skip)
    const orderModel = pos?.models?.["pos.order"];
    const allOrders = orderModel?.getAll?.() || orderModel?.records || [];

    for (const order of allOrders) {
      const ref = extractRef(order.pos_reference || "");
      if (!ref) continue; // ← SOLO skipear si no hay ref, NO por cache

      const state = (order.invoice_state || "no_invoice").trim();
      const label =
        (order.invoice_state_label || "").trim() ||
        STATE_LABELS[state] ||
        "Sin factura";

      // ✅ SIEMPRE actualizar (no verificar si existe en cache)
      invoiceStateCache.set(ref, { state, label });
    }

    // Renderizar badges
    for (const row of rows) {
      const receiptCol = findReceiptColumn(row);
      const ref = extractRef(receiptCol?.textContent || "");
      const cell = row.querySelector('[data-pos-invoice-state-col="1"]');
      if (!cell) continue;

      if (!ref) {
        cell.textContent = "-";
        cell.title = "";
        continue;
      }

      const info = invoiceStateCache.get(ref);
      if (info) {
        renderBadge(cell, info);
      }
    }
  } finally {
    isApplying = false;
  }
}

patch(TicketScreen.prototype, {
  setup() {
    super.setup(...arguments);

    onMounted(() => {
      ensureObserver(this);
      schedule(this, 220);
    });
    onPatched(() => {
      ensureObserver(this);
      schedule(this, 120);
    });
    onWillUnmount(() => {
      if (observer) observer.disconnect();
      observer = null;
      observedRoot = null;
    });
  },
});
