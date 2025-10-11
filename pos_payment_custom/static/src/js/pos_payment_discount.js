/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { Order } from "@point_of_sale/app/store/models";

// 🔹 Extendemos el modelo Order para aplicar descuento/recargo automáticamente
patch(Order.prototype, "pos_payment_cash_adjustment_order", {
  add_paymentline(paymentMethod, options) {
    const res = super.add_paymentline(paymentMethod, options);

    // Si el método de pago tiene ajuste activo
    if (paymentMethod.apply_adjustment && paymentMethod.name === "Efectivo") {
      const order = this;
      const total = order.get_total_with_tax();

      const value = paymentMethod.adjustment_value || 0;
      const adjustment =
        paymentMethod.adjustment_type === "discount"
          ? -total * (value / 100)
          : total * (value / 100);

      // Guardamos la línea de ajuste en el pedido
      const currentAdjustment = order
        .get_orderlines()
        .find((l) => l.get_product()?.display_name === "Ajuste Efectivo");

      // Si ya existe una línea de ajuste, la actualizamos
      if (currentAdjustment) {
        currentAdjustment.set_unit_price(adjustment);
      } else {
        const product = order.pos.db.get_product_by_name("Ajuste Efectivo");
        if (product) {
          order.add_product(product, { price: adjustment });
        } else {
          console.warn(
            "⚠️ Producto 'Ajuste Efectivo' no encontrado. Crealo para registrar el ajuste."
          );
        }
      }
    }

    return res;
  },
});
