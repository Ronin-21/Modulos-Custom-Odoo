/* @odoo-module */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";

patch(PaymentScreen.prototype, {
  async addPaymentLine(paymentMethod) {
    await super.addPaymentLine(paymentMethod);

    console.log("addPaymentLine llamado");
    console.log("paymentMethod:", paymentMethod);
    console.log("apply_adjustment:", paymentMethod.apply_adjustment);

    // Aplicar ajuste si el método de pago lo tiene configurado
    const order = this.pos.get_order();
    console.log("order:", order);

    if (order && paymentMethod.apply_adjustment) {
      const paymentLines = order.get_paymentlines();
      console.log("paymentLines:", paymentLines);

      if (paymentLines.length > 0) {
        const lastPaymentLine = paymentLines[paymentLines.length - 1];
        console.log("lastPaymentLine:", lastPaymentLine);
        this._applyPaymentAdjustment(lastPaymentLine, paymentMethod);
      }
    }
  },

  _applyPaymentAdjustment(paymentLine, paymentMethod) {
    const originalAmount = paymentLine.amount;

    if (
      !paymentMethod.apply_adjustment ||
      paymentMethod.adjustment_value === 0
    ) {
      return;
    }

    const adjustmentPercent = paymentMethod.adjustment_value;
    const adjustmentAmount = originalAmount * (adjustmentPercent / 100);
    let finalAmount = originalAmount;

    if (paymentMethod.adjustment_type === "discount") {
      finalAmount = originalAmount - adjustmentAmount;
    } else {
      finalAmount = originalAmount + adjustmentAmount;
    }

    // Actualizar el monto del pago
    paymentLine.set_amount(finalAmount);

    // Mostrar notificación visual
    const typeLabel =
      paymentMethod.adjustment_type === "discount" ? "Descuento" : "Recargo";
    const symbol = paymentMethod.adjustment_type === "discount" ? "-" : "+";
    const message = `${typeLabel} aplicado: ${adjustmentPercent.toFixed(
      2
    )}% (${symbol}$${Math.abs(adjustmentAmount).toFixed(2)})`;

    this.env.services.notification.add(message, {
      type: "info",
      duration: 4000,
    });
  },
});
