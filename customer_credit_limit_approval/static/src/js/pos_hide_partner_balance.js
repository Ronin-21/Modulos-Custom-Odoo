/** @odoo-module **/
import { registry } from "@web/core/registry";

const HIDE_CLASS = "balance-hide";

registry.category("services").add("pos_balance_gate_dom", {
  async start(env) {
    const pos = env.services?.pos;

    const mo = new MutationObserver(() => {
      const root = document.querySelector(".client-list");
      if (!root) return;
      const hide = !pos?.config?.show_partner_balance;
      root.classList.toggle(HIDE_CLASS, hide);
    });

    mo.observe(document.body, { childList: true, subtree: true });
    return {};
  },
});
