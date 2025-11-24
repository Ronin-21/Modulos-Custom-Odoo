/** @odoo-module **/
import { registry } from "@web/core/registry";

const HIDE_CLASS = "pos-balance-hidden";

registry.category("services").add("pos_balance_visibility", {
  // Esperamos explícitamente al servicio POS
  dependencies: ["pos"],
  async start(env, { pos }) {
    // Esperar a que el POS termine de cargar su data (config incluida)
    if (pos.ready && typeof pos.ready.then === "function") {
      await pos.ready;
    }

    const apply = () => {
      const show = !!pos.config?.show_partner_balance;
      // true => mostramos; false => ocultamos
      document.documentElement.classList.toggle(HIDE_CLASS, !show);
    };

    apply();

    // Fallback por si algo recarga la UI/caché; no molesta y evita “quedar colgado”
    setInterval(apply, 5000);

    return {};
  },
});
