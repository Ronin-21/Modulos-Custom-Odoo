/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PosStore } from "@point_of_sale/app/store/pos_store";

function applyDefaultNoInvoice(pos) {
  const order = pos?.get_order?.();
  if (order && !order.__invoice_default_applied) {
    order.set_to_invoice(false);
    order.__invoice_default_applied = true;
  }
}

// 1) Default al crear una orden nueva (cubre la mayoría de casos)
patch(PosStore.prototype, {
  addNewOrder() {
    const order = super.addNewOrder(...arguments);
    try {
      order?.set_to_invoice(false);
    } catch (e) {}
    return order;
  },

  // fallback por si en tu build existe con snake_case
  add_new_order() {
    const order = super.add_new_order(...arguments);
    try {
      order?.set_to_invoice(false);
    } catch (e) {}
    return order;
  },
});

// 2) Backup: al entrar a la pantalla de pago (después del render)
patch(PaymentScreen.prototype, {
  setup() {
    super.setup(...arguments);

    onMounted(() => {
      applyDefaultNoInvoice(this.pos);

      // por si algo lo pisa justo después, lo re-aplicamos en el próximo tick
      setTimeout(() => applyDefaultNoInvoice(this.pos), 0);
    });
  },
});
