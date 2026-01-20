/* @odoo-module */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

const MASK_TOTAL_DIGITS = 7; // 3 + 4
const MASK_REGEX = /^\d{3}-\d{4}$/;

function asArray(v) {
  if (!v) return [];
  if (Array.isArray(v)) return v;
  if (v.records && Array.isArray(v.records)) return v.records;
  return [];
}

function getOrder(screen) {
  return (
    screen.currentOrder ||
    screen.pos?.get_order?.() ||
    screen.env?.services?.pos?.get_order?.() ||
    null
  );
}

function getPaymentlines(order) {
  if (!order) return [];
  if (order.get_paymentlines) return asArray(order.get_paymentlines());
  return asArray(order.payment_ids || order.paymentlines);
}

function getMethodFromLine(screen, line) {
  const cand =
    line?.payment_method ||
    line?.paymentMethod ||
    line?.payment_method_id ||
    line?.payment_method_id?.id ||
    null;

  if (!cand) return null;
  if (typeof cand === "object") return cand;

  const id = Number(cand) || null;
  if (!id) return null;

  const pos = screen.pos || screen.env?.services?.pos;
  return (
    pos?.payment_methods_by_id?.[id] ||
    (Array.isArray(pos?.payment_methods)
      ? pos.payment_methods.find((m) => m.id === id)
      : null) ||
    null
  );
}

function findPaymentSummary() {
  const card = document.querySelector(".o_pos_cash_discount_card");
  const fromCard = card?.closest?.(".payment-summary");
  if (fromCard) return fromCard;
  return document.querySelector(".payment-summary");
}

function ensureContainer(summary) {
  let c = summary.querySelector(".o_pos_coupon_inputs_summary");
  if (!c) {
    c = document.createElement("div");
    c.className = "o_pos_coupon_inputs_summary";
    c.style.marginTop = "10px";
    c.style.padding = "12px";
    c.style.borderRadius = "12px";
    c.style.border = "1px solid rgba(0,0,0,0.10)";
    c.style.background = "rgba(0,0,0,0.02)";

    // Insertar debajo de la card si existe
    const card =
      summary.querySelector(".o_pos_cash_discount_card") ||
      document.querySelector(".o_pos_cash_discount_card");
    if (
      card &&
      card.parentNode &&
      card.closest(".payment-summary") === summary
    ) {
      card.parentNode.insertBefore(c, card.nextSibling);
    } else {
      summary.appendChild(c);
    }
  }
  return c;
}

function formatCoupon(raw) {
  const digits = String(raw || "")
    .replace(/\D/g, "")
    .slice(0, MASK_TOTAL_DIGITS);
  if (digits.length <= 3) return digits;
  return `${digits.slice(0, 3)}-${digits.slice(3)}`;
}

function isCompleteCoupon(value) {
  return MASK_REGEX.test(String(value || ""));
}

function buildCouponLines(screen) {
  const order = getOrder(screen);
  const lines = getPaymentlines(order);

  const couponLines = [];
  for (const line of lines) {
    const method = getMethodFromLine(screen, line);
    if (!method) continue;
    if (!method.requires_coupon) continue;

    const key = String(line.cid ?? line.id ?? line.uid ?? "");
    if (!key) continue;

    couponLines.push({ line, method, key });
  }
  return couponLines;
}

function renderRows(container, couponLines) {
  const keep = new Set(couponLines.map((x) => x.key));

  container.querySelectorAll(".o_pos_coupon_row").forEach((row) => {
    const cid = row.dataset.cid || "";
    if (cid && !keep.has(cid)) row.remove();
  });

  for (const { line, method, key } of couponLines) {
    let row = container.querySelector(`.o_pos_coupon_row[data-cid="${key}"]`);
    if (!row) {
      row = document.createElement("div");
      row.className = "o_pos_coupon_row";
      row.dataset.cid = key;
      row.style.display = "flex";
      row.style.flexDirection = "column";
      row.style.gap = "6px";
      row.style.marginTop = "10px";

      const label = document.createElement("div");
      label.style.fontSize = "12px";
      label.style.opacity = "0.85";
      label.textContent = `Nº Cupón — ${
        method?.name || "Método"
      } (formato: 123-1234)`;

      const input = document.createElement("input");
      input.type = "text";
      input.className = "o_pos_coupon_input";
      input.placeholder = "123-1234";
      input.maxLength = 8; // 3 + '-' + 4
      input.inputMode = "numeric";
      input.autocomplete = "off";
      input.style.width = "100%";
      input.style.padding = "10px 12px";
      input.style.borderRadius = "10px";
      input.style.border = "1px solid rgba(0,0,0,0.12)";

      input.addEventListener("input", (ev) => {
        const formatted = formatCoupon(ev?.target?.value || "");
        ev.target.value = formatted;
        line.coupon_number = formatted;
      });

      input.addEventListener("blur", (ev) => {
        const formatted = formatCoupon(ev?.target?.value || "");
        ev.target.value = formatted;
        line.coupon_number = formatted;
      });

      row.appendChild(label);
      row.appendChild(input);
      container.appendChild(row);
    }

    const input = row.querySelector("input.o_pos_coupon_input");
    if (input && document.activeElement !== input) {
      const formatted = formatCoupon(line.coupon_number || "");
      input.value = formatted;
      line.coupon_number = formatted;
    }
  }
}

if (!window.__pos_payment_custom_coupon_ui_loaded__) {
  window.__pos_payment_custom_coupon_ui_loaded__ = true;

  patch(PaymentScreen.prototype, {
    setup() {
      super.setup();
      onMounted(() => {
        this.__coupon_retry = 0;
        setTimeout(() => this.addCouponInputsToPaymentLines(), 80);
      });
    },

    addCouponInputsToPaymentLines() {
      const summary = findPaymentSummary();

      if (!summary) {
        this.__coupon_retry = (this.__coupon_retry || 0) + 1;
        if (this.__coupon_retry <= 12) {
          setTimeout(() => this.addCouponInputsToPaymentLines(), 150);
        }
        return;
      }

      const couponLines = buildCouponLines(this);

      const existing = summary.querySelector(".o_pos_coupon_inputs_summary");
      if (!couponLines.length) {
        if (existing) existing.remove();
        return;
      }

      const container = ensureContainer(summary);
      renderRows(container, couponLines);
    },

    async addNewPaymentLine(paymentMethod) {
      const res = await super.addNewPaymentLine(paymentMethod);
      setTimeout(() => this.addCouponInputsToPaymentLines(), 80);
      return res;
    },

    deletePaymentLine(ev) {
      const res = super.deletePaymentLine(ev);
      setTimeout(() => this.addCouponInputsToPaymentLines(), 80);
      return res;
    },

    deleteOrderline(...args) {
      const res = super.deleteOrderline(...args);
      setTimeout(() => this.addCouponInputsToPaymentLines(), 80);
      return res;
    },

    // ✅ Validación fuerte al validar el pedido
    async validateOrder(...args) {
      try {
        const order = getOrder(this);
        const lines = getPaymentlines(order);
        for (const line of lines) {
          const method = getMethodFromLine(this, line);
          if (!method || !method.requires_coupon) continue;

          // Solo exigir si la línea de pago realmente está usada
          if (!line.amount || Number(line.amount) === 0) continue;

          const formatted = formatCoupon(line.coupon_number || "");
          line.coupon_number = formatted;

          if (!isCompleteCoupon(formatted)) {
            window.alert(
              "Debe ingresar un Nº Cupón válido con formato 123-1234 para el método: " +
                (method.name || "")
            );
            return; // corta validación
          }
        }
      } catch (e) {
        // si algo falla, no bloqueamos venta por el validador
        console.error("[pos_payment_custom][coupon_ui] validate error:", e);
      }

      return await super.validateOrder(...args);
    },
  });
}
