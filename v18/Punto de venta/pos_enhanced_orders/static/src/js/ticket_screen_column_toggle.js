/* @odoo-module */

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted, onPatched, onWillUnmount } from "@odoo/owl";

let timer = null;
let rootObserver = null;
let screenObserver = null;
let observedRoot = null;

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
    if (r.querySelector(".header-row")) return r;
  }
  return document.querySelector(".orders") || null;
}

function setDisplay(el, show) {
  if (!el) return;
  el.style.display = show ? "" : "none";
}

function setDisplayAll(root, selector, show) {
  if (!root) return;
  root.querySelectorAll(selector).forEach((el) => setDisplay(el, show));
}

/**
 * 🔥 IMPORTANTÍSIMO:
 * borra los “rellenos” que estaban creando columnas fantasma y duplicando valores.
 */
function cleanupAutoPads(root) {
  if (!root) return;
  root.querySelectorAll('[data-pos-auto-pad="1"]').forEach((el) => el.remove());
}

/**
 * Asegura clases en headers POR TEXTO (sin tocar índices de filas).
 * Las filas ya suelen venir con clases pos-col-... en Odoo.
 */
function ensureHeaderClasses(root) {
  const headerRow = root?.querySelector(".header-row");
  if (!headerRow) return;

  const headers = Array.from(headerRow.children || []);
  for (const h of headers) {
    const t = (h.textContent || "").trim();

    if (/^fecha$/i.test(t)) h.classList.add("pos-col-date", "pos-col-left");
    if (/n[uú]mero de recibo/i.test(t))
      h.classList.add("pos-col-receipt", "pos-col-left");
    if (/n[uú]mero de orden/i.test(t))
      h.classList.add("pos-col-order", "pos-col-center");
    if (/^cliente$/i.test(t)) h.classList.add("pos-col-client", "pos-col-left");
    if (/^cajero$/i.test(t)) h.classList.add("pos-col-cashier", "pos-col-left");
    if (/^total$/i.test(t)) h.classList.add("pos-col-total", "pos-col-center");

    // ⚠️ No usar /estado/i porque matchea “Estado factura”
    if (/^estado$/i.test(t)) h.classList.add("pos-col-state", "pos-col-center");

    if (/^tabla$/i.test(t)) h.classList.add("pos-col-table", "pos-col-left");

    if (/estado\s+factura/i.test(t))
      h.classList.add("pos-col-invoice-state", "pos-col-center");

    if (/pagos|m[ée]todos de pago/i.test(t))
      h.classList.add("pos-col-payments", "pos-col-left");
  }
}

function ensureObservers(screen) {
  const root = findOrdersRoot();

  // Observer del root (cuando ya existe)
  if (root && observedRoot !== root) {
    if (rootObserver) rootObserver.disconnect();
    observedRoot = root;

    rootObserver = new MutationObserver(() => schedule(screen, 80));
    rootObserver.observe(root, { childList: true, subtree: true });

    // si había observer de pantalla, ya no hace falta
    if (screenObserver) {
      screenObserver.disconnect();
      screenObserver = null;
    }
  }

  // Observer de pantalla/body (cuando todavía NO existe .orders)
  if (!root && !screenObserver) {
    const screenEl = document.querySelector(".ticket-screen") || document.body;
    screenObserver = new MutationObserver(() => {
      const r = findOrdersRoot();
      if (r) {
        ensureObservers(screen);
        schedule(screen, 60);
      }
    });
    screenObserver.observe(screenEl, { childList: true, subtree: true });
  }
}

function apply(screen) {
  const pos = getPos(screen);
  const root = findOrdersRoot();
  if (!pos || !root) return;

  cleanupAutoPads(root);
  ensureHeaderClasses(root);

  const cfg = pos.config || {};

  // Base columns (default: visible)
  setDisplayAll(root, ".pos-col-date", cfg.show_ticket_col_date !== false);
  setDisplayAll(
    root,
    ".pos-col-receipt",
    cfg.show_ticket_col_receipt !== false,
  );
  setDisplayAll(root, ".pos-col-order", cfg.show_ticket_col_order !== false);
  setDisplayAll(root, ".pos-col-client", cfg.show_ticket_col_client !== false);
  setDisplayAll(
    root,
    ".pos-col-cashier",
    cfg.show_ticket_col_cashier !== false,
  );
  setDisplayAll(root, ".pos-col-total", cfg.show_ticket_col_total !== false);
  setDisplayAll(root, ".pos-col-state", cfg.show_ticket_col_state !== false);
  setDisplayAll(root, ".pos-col-table", cfg.show_ticket_col_table !== false);

  // Custom toggles (solo si están activados explícitamente)
  const showPayments = cfg.show_ticket_col_payments === true;
  const showInv = cfg.show_ticket_col_invoice_state === true;

  setDisplayAll(
    root,
    ".pos-col-payments, [data-pos-payments-col='1']",
    showPayments,
  );
  setDisplayAll(
    root,
    ".pos-col-invoice-state, [data-pos-invoice-state-col='1']",
    showInv,
  );
}

patch(TicketScreen.prototype, {
  setup() {
    super.setup(...arguments);

    onMounted(() => {
      ensureObservers(this);
      schedule(this, 200);
    });

    onPatched(() => {
      ensureObservers(this);
      schedule(this, 120);
    });

    onWillUnmount(() => {
      if (rootObserver) rootObserver.disconnect();
      if (screenObserver) screenObserver.disconnect();
      rootObserver = null;
      screenObserver = null;
      observedRoot = null;
    });
  },
});
