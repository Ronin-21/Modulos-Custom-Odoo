/* @odoo-module */

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted, onPatched } from "@odoo/owl";

let timer = null;
function schedule(screen, delay = 80) {
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

function findHeaderIndexByText(root, regex) {
  const headerRow = root?.querySelector(".header-row");
  if (!headerRow) return -1;
  const children = Array.from(headerRow.children || []);
  for (let i = 0; i < children.length; i++) {
    const t = (children[i]?.textContent || "").trim();
    if (regex.test(t)) return i;
  }
  return -1;
}

function setDisplay(el, show) {
  if (!el) return;
  el.style.display = show ? "" : "none";
}

function toggleColumnByHeader(root, headerRegex, show) {
  const idx = findHeaderIndexByText(root, headerRegex);
  if (idx < 0) return;

  const headerRow = root.querySelector(".header-row");
  setDisplay(headerRow?.children?.[idx], show);

  const rows = Array.from(root.querySelectorAll(".order-row") || []);
  for (const row of rows) {
    setDisplay(row?.children?.[idx], show);
  }
}

/* ===========================
   ✅ Alineación / Orden columnas
   =========================== */

const ALIGN_CLASSES = [
  "pos-col-left",
  "pos-col-center",
  "pos-col-right",
  "pos-col-date",
  "pos-col-receipt",
  "pos-col-order",
  "pos-col-client",
  "pos-col-cashier",
  "pos-col-total",
  "pos-col-coupon",
  "pos-col-state",
  "pos-col-table",
  "pos-col-payments",
];

function clearAlignClasses(root) {
  const nodes = root.querySelectorAll(".header-row .col, .order-row .col");
  for (const n of nodes) {
    for (const c of ALIGN_CLASSES) n.classList.remove(c);
  }
}

function tagColumn(root, headerRegex, classes) {
  const idx = findHeaderIndexByText(root, headerRegex);
  if (idx < 0) return;

  const headerRow = root.querySelector(".header-row");
  const headerCell = headerRow?.children?.[idx];
  if (headerCell) headerCell.classList.add(...classes);

  const rows = Array.from(root.querySelectorAll(".order-row") || []);
  for (const row of rows) {
    const cell = row?.children?.[idx];
    if (cell) cell.classList.add(...classes);
  }
}

function applyAlignment(root) {
  clearAlignClasses(root);

  // Ajustá estos regex si tu traducción cambia
  tagColumn(root, /fecha/i, ["pos-col-date", "pos-col-left"]);
  tagColumn(root, /n[uú]mero de recibo/i, ["pos-col-receipt", "pos-col-left"]);
  tagColumn(root, /n[uú]mero de orden/i, ["pos-col-order", "pos-col-center"]);
  tagColumn(root, /cliente/i, ["pos-col-client", "pos-col-left"]);
  tagColumn(root, /cajero/i, ["pos-col-cashier", "pos-col-left"]);
  tagColumn(root, /total/i, ["pos-col-total", "pos-col-right"]);
  tagColumn(root, /cup[oó]n/i, ["pos-col-coupon", "pos-col-center"]);
  tagColumn(root, /estado/i, ["pos-col-state", "pos-col-center"]);
  tagColumn(root, /mesa/i, ["pos-col-table", "pos-col-center"]);
  tagColumn(root, /pagos|m[ée]todos de pago/i, [
    "pos-col-payments",
    "pos-col-left",
  ]);
}

function apply(screen) {
  const pos = getPos(screen);
  const root = findOrdersRoot();
  if (!pos || !root) return;

  const cfg = pos.config || {};

  // Mostrar/ocultar (checks)
  toggleColumnByHeader(root, /cliente/i, cfg.show_ticket_col_client !== false);
  toggleColumnByHeader(root, /cajero/i, cfg.show_ticket_col_cashier !== false);
  toggleColumnByHeader(root, /total/i, cfg.show_ticket_col_total !== false);
  toggleColumnByHeader(root, /cup[oó]n/i, cfg.show_ticket_col_coupon !== false);
  toggleColumnByHeader(root, /estado/i, cfg.show_ticket_col_state !== false);
  toggleColumnByHeader(root, /mesa/i, cfg.show_ticket_col_table !== false);
  toggleColumnByHeader(root, /fecha/i, cfg.show_ticket_col_date !== false);
  toggleColumnByHeader(
    root,
    /n[uú]mero de recibo/i,
    cfg.show_ticket_col_receipt !== false,
  );
  toggleColumnByHeader(
    root,
    /n[uú]mero de orden/i,
    cfg.show_ticket_col_order !== false,
  );
  toggleColumnByHeader(
    root,
    /pagos|m[ée]todos de pago/i,
    cfg.show_ticket_col_payments === true,
  );

  // ✅ Alineación / anchos prolijos
  applyAlignment(root);
}

patch(TicketScreen.prototype, {
  setup() {
    super.setup();
    onMounted(() => schedule(this, 150));
    onPatched(() => schedule(this, 80));
  },
});
