/** @odoo-module **/

import { registry } from "@web/core/registry";

const MOD = "[pos_balance_gate]";
console.log("[pos_credit_limit] archivo cargado ✅");

// --- inyectamos CSS de respaldo (por si el SCSS no carga) ---
function ensureInlineStyle() {
  if (document.getElementById("pos-balance-hide-style")) return;
  const css = `
      /* ocultar por clase genérica */
      .pos-hide-partner-balance .pos-balance-col { display:none !important; }

      /* fallback por posición (4ta col: Nombre, Dirección, Contacto, Saldo) */
      .pos-hide-partner-balance .o_clientlist-screen table thead th:nth-child(4),
      .pos-hide-partner-balance .o_clientlist-screen table tbody td:nth-child(4),
      .pos-hide-partner-balance .clientlist-screen table thead th:nth-child(4),
      .pos-hide-partner-balance .clientlist-screen table tbody td:nth-child(4) {
        display:none !important;
      }
    `;
  const el = document.createElement("style");
  el.id = "pos-balance-hide-style";
  el.textContent = css;
  document.head.appendChild(el);
}

// --- detecta la columna “Saldo” por texto y la etiqueta ---
function markBalanceColumn(root) {
  const container = root || document;
  const tables = container.querySelectorAll(
    ".o_clientlist-screen table, .clientlist-screen table"
  );
  tables.forEach((table) => {
    const ths = table.querySelectorAll("thead th");
    if (!ths.length) return;

    // Buscar “Saldo” por texto (soporta traducciones: saldo, balance, due, adeudado, crédito)
    const candidates = [
      "saldo",
      "balance",
      "due",
      "adeudado",
      "crédito",
      "credito",
    ];
    let balanceIndex = -1;
    ths.forEach((th, i) => {
      const txt = (th.textContent || "").trim().toLowerCase();
      if (candidates.some((w) => txt.includes(w))) balanceIndex = i;
    });

    if (balanceIndex >= 0) {
      // Marcar header y todas las celdas de esa columna
      ths[balanceIndex]?.classList.add("pos-balance-col");
      table.querySelectorAll("tbody tr").forEach((tr) => {
        const td = tr.children[balanceIndex];
        if (td) td.classList.add("pos-balance-col");
      });
    }
  });
}

// --- observar cambios para re-aplicar al abrir el selector de clientes ---
function setupObserver() {
  if (window.__posBalanceObserver__) return;
  const obs = new MutationObserver((muts) => {
    for (const m of muts) {
      for (const node of m.addedNodes || []) {
        if (!(node instanceof HTMLElement)) continue;
        // ¿apareció la lista de clientes?
        if (
          node.matches(".o_clientlist-screen, .clientlist-screen") ||
          node.querySelector(".o_clientlist-screen, .clientlist-screen")
        ) {
          markBalanceColumn(node);
        }
      }
    }
  });
  obs.observe(document.body, { childList: true, subtree: true });
  window.__posBalanceObserver__ = obs;
}

registry.category("services").add("pos_balance_gate", {
  start(env) {
    const pos = env.services?.pos; // POS env
    ensureInlineStyle();
    setupObserver();

    const apply = () => {
      const show = !!pos?.config?.show_partner_balance;
      console.log(`${MOD} show_partner_balance =`, show);
      // cuando está en FALSE → agregamos la clase para ocultar
      document.body.classList.toggle("pos-hide-partner-balance", !show);
      if (!show) {
        // marcar la columna “Saldo” dinámica
        markBalanceColumn(document);
      }
    };

    // aplicar ahora y al montar servicios POS
    try {
      apply();
    } catch (e) {
      console.warn(`${MOD} apply() error`, e);
    }

    // Por si el POS reconfigura algo al cargar
    setTimeout(apply, 200);
    setTimeout(apply, 600);

    return {};
  },
});
