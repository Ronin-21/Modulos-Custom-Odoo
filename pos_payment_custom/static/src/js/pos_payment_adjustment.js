/* @odoo-module */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";

const DEBUG = false;

if (!window.__pos_payment_adjustment_loaded__) {
  window.__pos_payment_adjustment_loaded__ = true;

  const ORIGINAL = {
    setup: PaymentScreen.prototype.setup,
    addNewPaymentLine: PaymentScreen.prototype.addNewPaymentLine,
    deletePaymentLine: PaymentScreen.prototype.deletePaymentLine,
    validateOrder: PaymentScreen.prototype.validateOrder,
  };

  function dlog(...args) {
    if (DEBUG) console.log("[PAY_ADJ]", ...args);
  }
  function asArray(v) {
    return !v
      ? []
      : Array.isArray(v)
      ? v
      : v.records && Array.isArray(v.records)
      ? v.records
      : [];
  }
  function approx(a, b, eps = 0.01) {
    return Math.abs((Number(a) || 0) - (Number(b) || 0)) <= eps;
  }

  function getM2OId(v) {
    if (!v) return null;
    if (typeof v === "number") return v;
    if (Array.isArray(v)) return v[0];
    if (typeof v === "object" && typeof v.id === "number") return v.id;
    return null;
  }

  function formatCurrency(screen, amount) {
    const a = Number(amount || 0);
    try {
      if (screen?.env?.utils?.formatCurrency)
        return screen.env.utils.formatCurrency(a);
    } catch {}
    try {
      if (screen?.pos?.format_currency) return screen.pos.format_currency(a);
    } catch {}
    return a.toFixed(2);
  }

  function getDue(order) {
    if (order?.get_due) return Number(order.get_due()) || 0;
    const total = Number(order?.amount_total || 0);
    const paid = Number(order?.amount_paid || 0);
    return total - paid;
  }

  function getPaymentlines(order, screen) {
    const a = asArray(order?.payment_ids);
    const b = asArray(order?.paymentlines);
    const c = order?.get_paymentlines ? asArray(order.get_paymentlines()) : [];
    const d = asArray(screen?.paymentLines);
    return a.length ? a : b.length ? b : c.length ? c : d.length ? d : [];
  }

  function getLastPaymentline(order, screen) {
    const pls = getPaymentlines(order, screen);
    return pls.length ? pls[pls.length - 1] : null;
  }

  function resolveMethod(order, pl, forcedMethod = null) {
    const cand =
      pl?.payment_method ||
      pl?.paymentMethod ||
      pl?.payment_method_id ||
      pl?.payment_method_id?.id ||
      null;
    if (cand && typeof cand === "object") return cand;

    if (typeof cand === "number") {
      const avail = asArray(order?.available_payment_method_ids);
      const found = avail.find((m) => m.id === cand);
      if (found) return found;
    }
    return forcedMethod || null;
  }

  function getOrderlines(order) {
    return order?.get_orderlines ? order.get_orderlines() : order?.lines || [];
  }

  function getLineDiscount(line) {
    return line?.get_discount
      ? line.get_discount()
      : typeof line?.discount === "number"
      ? line.discount
      : 0;
  }
  function setLineDiscount(line, value) {
    const v = Math.max(0, Math.min(100, Number(value) || 0));
    if (line?.set_discount) return line.set_discount(v);
    if (line?.setDiscount) return line.setDiscount(v);
    line.discount = v;
  }

  function getPaymentLineAmount(pl) {
    if (pl?.get_amount) return Number(pl.get_amount() || 0);
    if (pl?.getAmount) return Number(pl.getAmount() || 0);
    return Number(pl?.amount || 0);
  }

  function setPaymentLineAmount(pl, value) {
    const v = Number(value) || 0;
    if (pl?.set_amount) return pl.set_amount(v);
    if (pl?.setAmount) return pl.setAmount(v);
    pl.amount = v;
  }

  function isEligible(method) {
    return (
      (method?.apply_adjustment === true &&
        Number(method?.adjustment_value || 0) > 0) ||
      (method?.apply_adjustment &&
        Array.isArray(method?.adjustment_options) &&
        method.adjustment_options.length)
    );
  }

  function isOrderEditable(order) {
    if (!order) return false;
    try {
      if (typeof order.is_editable === "function") return !!order.is_editable();
      if (typeof order.isEditable === "function") return !!order.isEditable();
      if (typeof order.assert_editable === "function") {
        order.assert_editable(); // si está finalizada, tira
        return true;
      }
    } catch {
      return false;
    }
    // fallback: si no hay métodos, asumimos editable
    return true;
  }

  function methodType(method) {
    return method?.adjustment_type || "discount";
  }

  // -----------------------------
  // DESCUENTO (en líneas)
  // -----------------------------
  function applyDiscount(order, percent) {
    const lines = getOrderlines(order);
    for (const line of lines) {
      if (line.__payAdjLine) continue; // no tocar recargo-producto
      const current = getLineDiscount(line);
      if (!line.__cashDiscApplied && current > 0) continue;
      if (!line.__cashDiscApplied) {
        line.__cashDiscOrigDiscount = current;
        line.__cashDiscApplied = true;
      }
      setLineDiscount(line, percent);
    }
  }

  function removeDiscount(order) {
    const lines = getOrderlines(order);
    for (const line of lines) {
      if (line.__cashDiscApplied) {
        setLineDiscount(line, Number(line.__cashDiscOrigDiscount || 0));
        delete line.__cashDiscApplied;
        delete line.__cashDiscOrigDiscount;
      }
    }
  }

  function computeDiscountAmount(order, percent) {
    if (!(percent > 0) || percent >= 100) return 0;
    const lines = getOrderlines(order).filter((l) => !!l.__cashDiscApplied);
    let discountedTotalWithTax = 0;

    for (const line of lines) {
      let v = 0;
      if (line?.get_price_with_tax) v = Number(line.get_price_with_tax()) || 0;
      else if (line?.get_price_with_tax_included)
        v = Number(line.get_price_with_tax_included()) || 0;
      else if (line?.get_display_price)
        v = Number(line.get_display_price()) || 0;
      discountedTotalWithTax += v;
    }
    return discountedTotalWithTax * (percent / (100 - percent));
  }

  // -----------------------------
  // RECARGO (producto)
  // -----------------------------
  function getProductById(screen, productId) {
    const pos = screen?.pos;
    const model = pos?.models?.["product.product"];
    if (model) {
      if (typeof model.get === "function") return model.get(productId);
      if (Array.isArray(model)) return model.find((p) => p.id === productId);
      if (Array.isArray(model.records))
        return model.records.find((p) => p.id === productId);
    }
    if (pos?.db?.get_product_by_id) return pos.db.get_product_by_id(productId);
    return null;
  }

  function removeSurchargeLines(order) {
    const lines = getOrderlines(order);
    for (const line of [...lines]) {
      if (line.__payAdjLine) {
        order.removeOrderline
          ? order.removeOrderline(line)
          : line.remove && line.remove();
      }
    }
  }

  function computeBaseTotalWithTax(order) {
    const lines = getOrderlines(order);
    let total = 0;
    for (const line of lines) {
      if (line.__payAdjLine) continue;
      let v = 0;
      if (line?.get_price_with_tax) v = Number(line.get_price_with_tax()) || 0;
      else if (line?.get_price_with_tax_included)
        v = Number(line.get_price_with_tax_included()) || 0;
      else if (line?.get_display_price)
        v = Number(line.get_display_price()) || 0;
      total += v;
    }
    return total;
  }

  function setLineUnitPrice(line, price) {
    const v = Number(price || 0);
    if (line?.set_unit_price) return line.set_unit_price(v);
    if (line?.setUnitPrice) return line.setUnitPrice(v);
    line.price_unit = v;
  }

  function setLineQty(line, qty) {
    const q = Number(qty || 1);
    if (line?.set_quantity) return line.set_quantity(q);
    if (line?.setQuantity) return line.setQuantity(q);
    line.quantity = q;
  }

  async function addOrUpdateSurcharge(screen, method, percent) {
    const order = screen.currentOrder;
    const productId = getM2OId(method?.adjustment_product_id);
    if (!productId) {
      removeSurchargeLines(order);
      return 0;
    }

    const product = getProductById(screen, productId);
    if (!product) {
      console.warn(
        "[PAY_ADJ] No encuentro el producto de recargo en el POS:",
        productId
      );
      removeSurchargeLines(order);
      return 0;
    }

    const base = computeBaseTotalWithTax(order);
    const amount = (base * percent) / 100.0;

    let line = getOrderlines(order).find((l) => l.__payAdjLine);
    if (!line) {
      if (order?.add_product) {
        order.add_product(product, {
          price_unit: amount,
          quantity: 1,
          merge: false,
        });
        const lines = getOrderlines(order);
        line = lines[lines.length - 1];
      } else if (screen.pos?.addLineToCurrentOrder) {
        await screen.pos.addLineToCurrentOrder({
          product_id: product,
          price_unit: amount,
          quantity: 1,
        });
        const lines = getOrderlines(order);
        line = lines[lines.length - 1];
      } else {
        console.warn(
          "[PAY_ADJ] No hay forma estándar de agregar la línea de recargo."
        );
        return amount;
      }
      if (line) line.__payAdjLine = true;
    }

    if (line) {
      line.__payAdjLine = true;
      setLineQty(line, 1);
      setLineDiscount(line, 0);
      setLineUnitPrice(line, amount);
    }

    return amount;
  }

  // Fix de cambio por pago auto
  function fixChangeIfAuto(order, screen) {
    const pls = getPaymentlines(order, screen);
    if (pls.length !== 1) return;
    const pl = pls[0];
    const due = getDue(order);
    const amt = getPaymentLineAmount(pl);

    if (
      due < -0.0001 &&
      pl.__payAdjAuto &&
      approx(amt, pl.__payAdjAutoAmount)
    ) {
      const newAmount = amt + due;
      setPaymentLineAmount(pl, newAmount);
      pl.__payAdjAutoAmount = getPaymentLineAmount(pl);
    }
  }

  // Cuando el total sube (recargo) y el pago es auto, completar el restante
  function fillRemainingIfAuto(order, screen) {
    const pls = getPaymentlines(order, screen);
    if (pls.length !== 1) return;

    const pl = pls[0];
    const due = getDue(order); // lo que falta pagar (positivo)
    const amt = getPaymentLineAmount(pl);

    if (!(due > 0.0001)) return; // nada que completar
    if (!pl.__payAdjAuto) return; // solo para pagos auto

    // Si el usuario tocó el monto, no lo pisamos
    if (
      pl.__payAdjAutoAmount !== undefined &&
      pl.__payAdjAutoAmount !== null &&
      !approx(amt, pl.__payAdjAutoAmount, 0.02)
    ) {
      return;
    }

    const newAmount = amt + due;
    setPaymentLineAmount(pl, newAmount);

    // actualizar referencia de "auto" para futuros cambios
    pl.__payAdjAutoAmount = getPaymentLineAmount(pl);
  }

  function updatePaymentMethodHighlight(screen) {
    if (!screen?.el) return;
    const order = screen.currentOrder;
    const pls = getPaymentlines(order, screen);
    const methods = pls
      .map((pl) => resolveMethod(order, pl, null))
      .filter(Boolean);

    const selectedIds = new Set(methods.map((m) => m.id));
    const selectedNames = new Set(methods.map((m) => (m.name || "").trim()));

    const buttons = screen.el.querySelectorAll(
      "[data-payment-method-id], [data-id], .paymentmethod, .payment-method, button"
    );
    buttons.forEach((btn) => {
      const did =
        Number(btn?.dataset?.paymentMethodId || btn?.dataset?.id || 0) || 0;
      const text = (btn?.innerText || "").trim();
      const isSelected =
        (did && selectedIds.has(did)) || (!!text && selectedNames.has(text));
      btn.classList.toggle("o_pos_paymentmethod_selected", isSelected);
    });
  }

  function pickOption(method, selectedId) {
    const opts = Array.isArray(method?.adjustment_options)
      ? method.adjustment_options
      : [];
    if (!opts.length) return null;
    const found = opts.find((o) => Number(o.id) === Number(selectedId));
    return found || opts[0];
  }

  async function recompute(screen, forcedMethod = null) {
    const order = screen?.currentOrder;
    if (!order) return;

    // ✅ si está finalizada/locked, NO tocar líneas ni pagos
    if (!isOrderEditable(order)) return;

    const pls = getPaymentlines(order, screen);
    const methods = pls
      .map((pl) => resolveMethod(order, pl, forcedMethod))
      .filter(Boolean);

    const unique = new Set(methods.map((m) => m.id || m.name));
    const method = methods[0];
    const allSame = method && unique.size === 1;

    // flags UI
    order.__payAdjActive = false;
    order.__payAdjType = "none";
    order.__payAdjPercent = 0;
    order.__payAdjAmount = 0;
    order.__payAdjMethodName = "";

    if (!allSame || !method || !isEligible(method)) {
      removeDiscount(order);
      removeSurchargeLines(order);
      fixChangeIfAuto(order, screen);
      updatePaymentMethodHighlight(screen);
      screen.render?.();
      return;
    }

    const type = methodType(method);

    // Si recargo con opciones: elegir opción
    let percent = Number(method?.adjustment_value || 0);
    const hasOpts =
      Array.isArray(method?.adjustment_options) &&
      method.adjustment_options.length;

    if (type === "surcharge" && hasOpts) {
      const opt = pickOption(method, order.__payAdjSelectedOptionId);
      order.__payAdjSelectedOptionId = opt?.id;
      percent = Number(opt?.percent || 0);
      order.__payAdjSelectedOptionName = opt?.name || "";
    } else {
      // si no hay opciones, limpiamos nombre
      order.__payAdjSelectedOptionName = "";
    }

    if (!(percent > 0)) {
      removeDiscount(order);
      removeSurchargeLines(order);
      fixChangeIfAuto(order, screen);
      updatePaymentMethodHighlight(screen);
      screen.render?.();
      return;
    }

    if (type === "surcharge") {
      removeDiscount(order);
      const amt = await addOrUpdateSurcharge(screen, method, percent);

      order.__payAdjActive = true;
      order.__payAdjType = "surcharge";
      order.__payAdjPercent = percent;
      order.__payAdjAmount = amt;
      order.__payAdjMethodName = method?.name || "Método";

      // ✅ NUEVO: si subió el total por recargo, completar el restante en la tarjeta
      fillRemainingIfAuto(order, screen);

      // ✅ EXISTENTE: si luego baja (cambio de opción / quito recargo) ajusta el cambio
      fixChangeIfAuto(order, screen);

      updatePaymentMethodHighlight(screen);
      screen.render?.();
      return;
    }

    // discount
    removeSurchargeLines(order);
    applyDiscount(order, percent);

    const damt = computeDiscountAmount(order, percent);
    order.__payAdjActive = true;
    order.__payAdjType = "discount";
    order.__payAdjPercent = percent;
    order.__payAdjAmount = damt;
    order.__payAdjMethodName = method?.name || "Método";

    fixChangeIfAuto(order, screen);
    updatePaymentMethodHighlight(screen);
    screen.render?.();
  }

  function recomputeTwice(screen, forcedMethod) {
    const orderRef = screen?.currentOrder;

    recompute(screen, forcedMethod);

    setTimeout(() => {
      // ✅ si cambió la orden o ya no es editable, no hacer nada
      if (!orderRef) return;
      if (screen.currentOrder !== orderRef) return;
      if (!isOrderEditable(orderRef)) return;

      recompute(screen, forcedMethod);
    }, 0);
  }

  patch(PaymentScreen.prototype, {
    setup() {
      const res = ORIGINAL.setup
        ? ORIGINAL.setup.apply(this, arguments)
        : undefined;
      setTimeout(() => recomputeTwice(this, null), 0);
      return res;
    },

    // UI: change option
    onPayAdjOptionChange(ev) {
      const id = Number(ev?.target?.value || 0) || null;
      this.currentOrder.__payAdjSelectedOptionId = id;
      recomputeTwice(this, null);
    },

    // Getters para template
    get payAdjActive() {
      const o = this.currentOrder;
      return !!o?.__payAdjActive && Number(o?.__payAdjAmount || 0) > 0;
    },
    get payAdjType() {
      return this.currentOrder?.__payAdjType || "none";
    },
    get payAdjMethodName() {
      return this.currentOrder?.__payAdjMethodName || "";
    },

    get payAdjHasOptions() {
      const method = this._payAdjCurrentMethod;
      return !!(
        method &&
        Array.isArray(method.adjustment_options) &&
        method.adjustment_options.length &&
        this.payAdjType === "surcharge"
      );
    },
    get payAdjOptions() {
      const method = this._payAdjCurrentMethod;
      return Array.isArray(method?.adjustment_options)
        ? method.adjustment_options
        : [];
    },
    get payAdjSelectedOptionId() {
      return Number(this.currentOrder?.__payAdjSelectedOptionId || 0) || null;
    },

    get payAdjTitle() {
      const t = this.currentOrder?.__payAdjType;
      if (t === "surcharge") return "Recargo por método de pago";
      if (t === "discount") return "Descuento por método de pago";
      return "Ajuste por método de pago";
    },
    get payAdjMeta() {
      const o = this.currentOrder;
      const t = o?.__payAdjType;
      const pct = Number(o?.__payAdjPercent || 0);
      const optName = (o?.__payAdjSelectedOptionName || "").trim();

      if (t === "surcharge") {
        const extra = optName ? ` • ${optName}` : "";
        return `${pct}%${extra}`;
      }
      if (t === "discount") {
        return `${pct}%`;
      }
      return "";
    },
    get payAdjAmountFormatted() {
      const o = this.currentOrder;
      const amt = Number(o?.__payAdjAmount || 0);
      const t = o?.__payAdjType;
      const sign = t === "surcharge" ? "+" : "-";
      return `${sign} ${formatCurrency(this, amt)}`;
    },

    get _payAdjCurrentMethod() {
      const order = this.currentOrder;
      const pls = getPaymentlines(order, this);
      const methods = pls
        .map((pl) => resolveMethod(order, pl, null))
        .filter(Boolean);
      const unique = new Set(methods.map((m) => m.id || m.name));
      if (methods.length && unique.size === 1) return methods[0];
      return null;
    },

    async addNewPaymentLine(paymentMethod) {
      const res = await ORIGINAL.addNewPaymentLine.apply(this, arguments);

      const pl = getLastPaymentline(this.currentOrder, this);
      if (pl) {
        pl.__payAdjAuto = true;
        pl.__payAdjAutoAmount = getPaymentLineAmount(pl);
      }

      recomputeTwice(this, paymentMethod);
      return res;
    },

    deletePaymentLine() {
      const res = ORIGINAL.deletePaymentLine.apply(this, arguments);
      recomputeTwice(this, null);
      return res;
    },

    async validateOrder() {
      // ✅ solo una vez, sin setTimeout que puede caer post-finalización
      await recompute(this, null);
      return await ORIGINAL.validateOrder.apply(this, arguments);
    },
  });
}
