/* @odoo-module */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

const DEBUG = false; // Cambiar a true para logs detallados

if (!window.__pos_payment_adjustment_loaded__) {
  window.__pos_payment_adjustment_loaded__ = true;

  const ORIGINAL = {
    setup: PaymentScreen.prototype.setup,
    addNewPaymentLine: PaymentScreen.prototype.addNewPaymentLine,
    deletePaymentLine: PaymentScreen.prototype.deletePaymentLine,
    deleteOrderline: PaymentScreen.prototype.deleteOrderline,
    validateOrder: PaymentScreen.prototype.validateOrder,
    // Opcionales (según versión de POS): si existen, los usaremos para recalcular
    updateSelectedPaymentline: PaymentScreen.prototype.updateSelectedPaymentline,
    selectPaymentLine: PaymentScreen.prototype.selectPaymentLine,
    selectPaymentline: PaymentScreen.prototype.selectPaymentline,
    onKeypadInput: PaymentScreen.prototype.onKeypadInput,

  };

  // Guard: evita crash si el buffer numérico intenta reproducir un sonido inexistente (sound undefined)
  function ensureNumberKeyboardSound(screen) {
    try {
      const kb =
        screen?.numberBuffer ||
        screen?.numberKeyboardBuffer ||
        screen?.number_keyboard_buffer ||
        screen?.env?.services?.number_keyboard_buffer ||
        screen?.env?.services?.numberBuffer ||
        screen?.env?.services?.number_keyboard ||
        screen?.env?.services?.numberbuffer;

      if (!kb) return;

      const proto = Object.getPrototypeOf(kb);
      if (!proto || typeof proto._updateBuffer !== "function") return;
      if (proto.__payAdjSoundGuardPatched) return;

      const _origUpdate = proto._updateBuffer;
      proto._updateBuffer = function () {
        // Algunos builds usan this.sound; si no existe, ponemos un stub
        if (!this.sound) {
          this.sound = this._sound || this.keypadSound || this.keyPressSound;
        }
        if (!this.sound) {
          this.sound = { play: () => {} };
        }
        if (this.sound && typeof this.sound.play !== "function") {
          this.sound.play = () => {};
        }

        try {
          return _origUpdate.apply(this, arguments);
        } catch (err) {
          const msg = err?.message ? String(err.message) : String(err);
          // Si el crash viene de .play() sobre undefined, reintentamos con stub
          if (msg && msg.includes("play")) {
            const prevSound = this.sound;
            this.sound = { play: () => {} };
            try {
              return _origUpdate.apply(this, arguments);
            } finally {
              this.sound = prevSound;
            }
          }
          throw err;
        }
      };

      proto.__payAdjSoundGuardPatched = true;
    } catch (e) {
      // no-op
    }
  }

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

  function getSelectedPaymentline(order, screen) {
    if (!order) return null;
    // API de Odoo (varía por versión)
    try {
      if (typeof order.get_selected_paymentline === "function") {
        return order.get_selected_paymentline();
      }
      if (typeof order.getSelectedPaymentline === "function") {
        return order.getSelectedPaymentline();
      }
    } catch {
      /* ignore */
    }

    // Propiedad directa (fallback)
    const direct = order.selected_paymentline || order.selectedPaymentline || null;
    if (direct) return direct;

    // Buscar un flag de selección en la colección
    const pls = getPaymentlines(order, screen);
    const found = pls.find(
      (pl) => !!pl?.selected || !!pl?.is_selected || !!pl?.isSelected
    );
    return found || getLastPaymentline(order, screen);
  }

  function trySelectPaymentline(screen, pl) {
    const order = screen?.currentOrder;
    if (!screen || !order || !pl) return;
    try {
      if (typeof screen.selectPaymentLine === "function") {
        screen.selectPaymentLine(pl);
        return;
      }
      if (typeof screen.selectPaymentline === "function") {
        screen.selectPaymentline(pl);
        return;
      }
    } catch {
      /* ignore */
    }
    try {
      if (typeof order.select_paymentline === "function") {
        order.select_paymentline(pl);
        return;
      }
    } catch {
      /* ignore */
    }
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

  // === Recargo en pagos mixtos (solo sobre lo pagado con tarjeta) ===
  // Estrategia:
  // - El recargo se calcula por cada paymentline de tarjeta (según su plan %).
  // - Para que el operador NO tenga que “hacer la cuenta” en mixtos, cuando un %
  //   pasa de 0 a >0 (o cuando la línea es autofill) interpretamos el importe
  //   ingresado/auto como BASE y lo convertimos a BRUTO (base + recargo).
  // - Luego el recargo de esa línea se obtiene como: bruto * p / (100 + p)
  //   (equivale a base * p / 100).
  function baseFromGross(gross, percent) {
    const g = Number(gross || 0);
    const p = Number(percent || 0);
    if (!(p > 0)) return g;
    return (g * 100) / (100 + p);
  }

  function grossFromBase(base, percent) {
    const b = Number(base || 0);
    const p = Number(percent || 0);
    if (!(p > 0)) return b;
    return (b * (100 + p)) / 100;
  }

  // Ajusta el amount de una paymentline de tarjeta para que represente el BRUTO
  // (base + recargo) de forma estable (sin “doble” recargo) y soportando cambios
  // de plan (%).
  function ensureCardPaymentlineGross(pl, percent) {
    if (!pl) return 0;
    const p = Number(percent || 0);
    let gross = getPaymentLineAmount(pl);
    if (!(gross > 0) || !(p > 0)) {
      pl.__payAdjPrevPercent = p;
      pl.__payAdjLastGrossSet = gross;
      // mantenemos base cache como el propio gross cuando no hay recargo
      pl.__payAdjBaseCache = gross;
      return gross;
    }

    const prevP = Number(pl.__payAdjPrevPercent || 0);
    const lastSet = pl.__payAdjLastGrossSet;

    // ¿El usuario tocó el importe manualmente desde la última vez?
    const userChanged =
      lastSet !== undefined && lastSet !== null && !approx(gross, lastSet, 0.02);

    // Base “verdadera” que usamos para mantener estable cuando cambia el %
    let base =
      typeof pl.__payAdjBaseCache === "number" ? pl.__payAdjBaseCache : null;

    if (userChanged) {
      // Si el usuario escribe un importe con % ya activo, lo interpretamos como BRUTO
      base = baseFromGross(gross, p);
    }

    // Caso típico: el % se activa (prevP=0) y el importe actual es BASE (ej: remaining)
    // o la línea fue autofill y aún no la “ajustamos” a bruto.
    const shouldAssumeBaseNow =
      (!userChanged && prevP !== p && base === null) ||
      (!!pl.__payAdjAuto &&
        !pl.__payAdjAutoGrossApplied &&
        pl.__payAdjAutoAmount !== undefined &&
        pl.__payAdjAutoAmount !== null &&
        approx(gross, pl.__payAdjAutoAmount, 0.02));

    if (shouldAssumeBaseNow) {
      base = gross;
      const newGross = grossFromBase(base, p);
      setPaymentLineAmount(pl, newGross);
      gross = getPaymentLineAmount(pl);
      pl.__payAdjAutoGrossApplied = true;
      if (pl.__payAdjAuto) {
        pl.__payAdjAutoAmount = gross;
      }
    }

    // Si ya tenemos base cache y cambió el plan (%), recalculamos el bruto.
    if (!shouldAssumeBaseNow && base !== null && prevP !== p) {
      const newGross = grossFromBase(base, p);
      setPaymentLineAmount(pl, newGross);
      gross = getPaymentLineAmount(pl);
      if (pl.__payAdjAuto) {
        pl.__payAdjAutoAmount = gross;
      }
    }

    // Si aún no hay base cache (y no aplicó el caso “asumir base”), derivarla del bruto.
    if (base === null) {
      base = baseFromGross(gross, p);
    }

    // Guardar caches
    pl.__payAdjBaseCache = base;
    pl.__payAdjLastGrossSet = gross;
    pl.__payAdjPrevPercent = p;

    return gross;
  }

  // ✅ Obtener todas las tarjetas del método
  function getMethodCards(method) {
    if (Array.isArray(method?.cards_config)) {
      return method.cards_config;
    }
    return [];
  }

  // ✅ Obtener opciones de una tarjeta específica
  function getCardOptions(card) {
    if (Array.isArray(card?.options)) {
      return card.options;
    }
    return [];
  }

  // ✅ Verificar si el método tiene tarjetas configuradas
  function isEligible(method) {
    if (!method?.apply_adjustment) {
      return false;
    }

    const cards = getMethodCards(method);
    if (cards.length > 0) {
      dlog("Eligible - has cards:", method?.name, cards.length);
      return true;
    }

    // Fallback: método sin tarjetas pero con porcentaje
    const hasPercent = Number(method?.adjustment_value || 0) > 0;
    return hasPercent;
  }

  function isOrderEditable(order) {
    if (!order) return false;
    try {
      if (typeof order.is_editable === "function") return !!order.is_editable();
      if (typeof order.isEditable === "function") return !!order.isEditable();
      if (typeof order.assert_editable === "function") {
        order.assert_editable();
        return true;
      }
    } catch {
      return false;
    }
    return true;
  }

  function methodType(method) {
    return method?.adjustment_type || "discount";
  }

  // DESCUENTO (en líneas)
  function applyDiscount(order, percent) {
    const lines = getOrderlines(order);
    for (const line of lines) {
      if (line.__payAdjLine) continue;
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

  // RECARGO (producto)
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

  function removeSurchargeLines(order, methodId = null) {
    const lines = getOrderlines(order);
    for (const line of [...lines]) {
      if (line.__payAdjLine && (!methodId || line.__payAdjMethodId === methodId)) {
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

  async function addOrUpdateSurchargeAmount(screen, method, amount) {
    const order = screen.currentOrder;
    const productId = getM2OId(method?.adjustment_product_id);

    const mid = method?.id || method?.name || null;
    if (!(amount > 0) || !productId) {
      removeSurchargeLines(order, mid);
      return 0;
    }

    const product = getProductById(screen, productId);
    if (!product) {
      console.warn("[PAY_ADJ] No encuentro el producto de recargo:", productId);
      removeSurchargeLines(order, mid);
      return 0;
    }

    let line = getOrderlines(order).find(
      (l) => l.__payAdjLine && l.__payAdjMethodId === mid
    );

    if (!line) {
      // ✅ ODOO 18: Usar la API correcta para agregar productos
      try {
        // Método 1: addProductToCurrentOrder (Odoo 18)
        if (screen.pos?.addProductToCurrentOrder) {
          await screen.pos.addProductToCurrentOrder(product, {
            price: amount,
            quantity: 1,
            merge: false,
          });
        }
        // Método 2: add_product_to_order (alternativo)
        else if (order?.add_product_to_order) {
          await order.add_product_to_order(product, {
            price: amount,
            quantity: 1,
            merge: false,
          });
        }
        // Método 3: Crear línea manualmente
        else {
          const Orderline = screen.pos.models["pos.order.line"];
          const lineData = {
            order_id: order,
            product_id: product,
            price_unit: amount,
            qty: 1,
            discount: 0,
          };

          if (Orderline && typeof Orderline.create === "function") {
            line = Orderline.create(lineData);
          } else {
            // Fallback: agregar directamente a las líneas
            const newLine = {
              id: `temp_${Date.now()}`,
              product_id: product,
              price_unit: amount,
              quantity: 1,
              qty: 1,
              discount: 0,
              __payAdjLine: true,
              __payAdjReadonly: true,
            };

            if (Array.isArray(order.lines)) {
              order.lines.push(newLine);
            } else if (order.lines?.add) {
              order.lines.add(newLine);
            }
            line = newLine;
          }
        }

        // Buscar la línea recién creada
        const lines = getOrderlines(order);
        line = lines[lines.length - 1];
      } catch (error) {
        console.error("[PAY_ADJ] Error agregando producto:", error);
        return amount;
      }

      if (line) {
        line.__payAdjLine = true;
        line.__payAdjReadonly = true;
        line.__payAdjMethodId = mid;
      }
    }

    if (line) {
      line.__payAdjLine = true;
      line.__payAdjReadonly = true;
      line.__payAdjMethodId = mid;
      setLineQty(line, 1);
      setLineDiscount(line, 0);
      setLineUnitPrice(line, amount);
    }

    return line?.get_price_with_tax?.() || amount;
  }

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

  function fillRemainingIfAuto(order, screen) {
    const pls = getPaymentlines(order, screen);
    if (pls.length !== 1) return;

    const pl = pls[0];
    const due = getDue(order);
    const amt = getPaymentLineAmount(pl);

    if (!(due > 0.0001)) return;
    if (!pl.__payAdjAuto) return;

    if (
      pl.__payAdjAutoAmount !== undefined &&
      pl.__payAdjAutoAmount !== null &&
      !approx(amt, pl.__payAdjAutoAmount, 0.02)
    ) {
      return;
    }

    const newAmount = amt + due;
    setPaymentLineAmount(pl, newAmount);
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

  // ✅ Encontrar tarjeta por ID
  function findCard(method, cardId) {
    const cards = getMethodCards(method);
    return (
      cards.find((c) => Number(c.id) === Number(cardId)) || cards[0] || null
    );
  }

  // ✅ Encontrar opción por ID en una tarjeta específica
  function findOption(card, optionId) {
    const options = getCardOptions(card);
    return (
      options.find((o) => Number(o.id) === Number(optionId)) ||
      options[0] ||
      null
    );
  }

  function ensureLineSelection(order, method, pl) {
    const cards = getMethodCards(method);
    if (!cards.length) {
      return { card: null, option: null, percent: 0, cardId: null, optionId: null };
    }

    let cardId = Number(pl?.__payAdjCardId || order?.__payAdjSelectedCardId || 0) || null;
    const card = findCard(method, cardId);
    if (card && Number(card.id) !== Number(cardId)) {
      cardId = card.id;
      if (pl) pl.__payAdjCardId = cardId;
    }

    const options = getCardOptions(card);
    let optionId = Number(pl?.__payAdjOptionId || order?.__payAdjSelectedOptionId || 0) || null;
    let option = null;
    if (options.length) {
      option = options.find((o) => Number(o.id) === Number(optionId)) || options[0];
      if (option && Number(option.id) !== Number(optionId)) {
        optionId = option.id;
        if (pl) pl.__payAdjOptionId = optionId;
      }
    }

    return {
      card,
      option,
      percent: Number(option?.percent || 0),
      cardId,
      optionId,
    };
  }

  async function recompute(screen, forcedMethod = null) {
    const order = screen?.currentOrder;
    if (!order) return;
    if (!isOrderEditable(order)) return;

    const pls = getPaymentlines(order, screen);
    const methods = pls
      .map((pl) => resolveMethod(order, pl, forcedMethod))
      .filter(Boolean);

    const unique = new Set(methods.map((m) => m.id || m.name));

    // --- MODO DESCUENTO (solo válido cuando hay 1 método) ---
    const onlyMethod = unique.size === 1 ? methods[0] : null;
    if (onlyMethod && isEligible(onlyMethod) && methodType(onlyMethod) === "discount") {
      // En descuento no usamos líneas de recargo
      removeSurchargeLines(order);

      const selectedPl = getSelectedPaymentline(order, screen) || getLastPaymentline(order, screen);
      const sel = getMethodCards(onlyMethod).length
        ? ensureLineSelection(order, onlyMethod, selectedPl)
        : { card: null, option: null, percent: 0 };
      const percent = Number(sel.percent || 0);

      // Estado base UI
      order.__payAdjTotalSurcharge = 0;
      order.__payAdjActive = false;
      order.__payAdjType = "none";
      order.__payAdjPercent = 0;
      order.__payAdjAmount = 0;
      order.__payAdjMethodName = onlyMethod?.name || "";
      order.__payAdjSelectedCardName = sel.card?.name || "";
      order.__payAdjSelectedOptionName = sel.option?.name || "";

      if (percent > 0) {
        applyDiscount(order, percent);
        const damt = computeDiscountAmount(order, percent);
        order.__payAdjActive = true;
        order.__payAdjType = "discount";
        order.__payAdjPercent = percent;
        order.__payAdjAmount = damt;
      } else {
        removeDiscount(order);
      }

      fixChangeIfAuto(order, screen);
      updatePaymentMethodHighlight(screen);
      screen.render?.();
      return;
    }

    // Estado base
    order.__payAdjTotalSurcharge = 0;
    order.__payAdjActive = false;
    order.__payAdjType = "none";
    order.__payAdjPercent = 0;
    order.__payAdjAmount = 0;
    order.__payAdjMethodName = unique.size > 1 ? "Mixto" : methods[0]?.name || "";
    order.__payAdjSelectedCardName = "";
    order.__payAdjSelectedOptionName = "";

    // En modo recargo (tarjetas) no aplicamos descuento en líneas
    removeDiscount(order);

    // Calcular recargos por líneas (soporta pagos mixtos)
    const surchargeByMethod = new Map();

    for (const pl of pls) {
      const method = resolveMethod(order, pl, forcedMethod);
      if (!method) continue;
      if (!isEligible(method)) continue;
      if (methodType(method) !== "surcharge") continue;

      const cards = getMethodCards(method);
      if (!cards.length) continue;

      const sel = ensureLineSelection(order, method, pl);
      const percent = Number(sel.percent || 0);
      // Asegurar que el amount de la línea de tarjeta represente el BRUTO
      // (base + recargo) antes de calcular el recargo.
      const paid = ensureCardPaymentlineGross(pl, percent);

      if (!(percent > 0) || !(paid > 0)) continue;

      // Si el pago incluye recargo, aislamos solo la porción de recargo:
      // recargo = pago * percent / (100 + percent)
      const lineSurcharge = (paid * percent) / (100 + percent);
      const key = method.id || method.name;
      surchargeByMethod.set(key, (surchargeByMethod.get(key) || 0) + lineSurcharge);
    }

    // Aplicar/actualizar líneas de recargo por método
    // 1) borrar las que ya no aplican
    const existingAdj = getOrderlines(order).filter((l) => !!l.__payAdjLine);
    for (const line of existingAdj) {
      const mid = line.__payAdjMethodId;
      if (!surchargeByMethod.has(mid)) {
        removeSurchargeLines(order, mid);
      }
    }

    // 2) crear/actualizar las necesarias
    let totalSurcharge = 0;
    for (const [mid, amt] of surchargeByMethod.entries()) {
      const method = methods.find((m) => (m.id || m.name) === mid) || null;
      if (!method) continue;
      const withTax = await addOrUpdateSurchargeAmount(screen, method, amt);
      totalSurcharge += Number(withTax || 0);
    }

    order.__payAdjTotalSurcharge = totalSurcharge;

    // Si hay métodos mixtos, no aplicamos descuento a nivel de líneas (evita cálculos incorrectos)
    if (unique.size !== 1) {
      removeDiscount(order);
    }

    // Datos para la UI (se basan en la paymentline seleccionada)
    const selectedPl = getSelectedPaymentline(order, screen);
    const selectedMethod = resolveMethod(order, selectedPl, null);
    if (selectedMethod && isEligible(selectedMethod) && getMethodCards(selectedMethod).length) {
      const sel = ensureLineSelection(order, selectedMethod, selectedPl);
      order.__payAdjType = methodType(selectedMethod);
      order.__payAdjPercent = Number(sel.percent || 0);
      order.__payAdjSelectedCardName = sel.card?.name || "";
      order.__payAdjSelectedOptionName = sel.option?.name || "";
      order.__payAdjMethodName = selectedMethod?.name || order.__payAdjMethodName;
    } else {
      order.__payAdjType = totalSurcharge > 0 ? "surcharge" : "none";
    }

    // Monto mostrado: total de recargo (si existe), si no, el calculado por descuento/recargo clásico
    order.__payAdjAmount = totalSurcharge;
    order.__payAdjActive = totalSurcharge > 0 || (!!selectedMethod && getMethodCards(selectedMethod).length);

    // Si hay una sola línea de pago con auto-fill, ajustar por el recargo agregado
    fillRemainingIfAuto(order, screen);

    fixChangeIfAuto(order, screen);
    updatePaymentMethodHighlight(screen);
    screen.render?.();
  }

  function recomputeTwice(screen, forcedMethod) {
    const orderRef = screen?.currentOrder;

    recompute(screen, forcedMethod);

    setTimeout(() => {
      if (!orderRef) return;
      if (screen.currentOrder !== orderRef) return;
      if (!isOrderEditable(orderRef)) return;

      recompute(screen, forcedMethod);
    }, 0);
  }

  function validateCouponNumbers(screen) {
    const order = screen.currentOrder;
    if (!order) return { valid: true };

    const pls = getPaymentlines(order, screen);

    for (const pl of pls) {
      const method = resolveMethod(order, pl, null);
      if (!method) continue;

      // Puede ser a nivel método (legacy) o a nivel tarjeta (nuevo)
      let requires = !!method.requires_coupon;

      if (getMethodCards(method).length) {
        const sel = ensureLineSelection(order, method, pl);
        if (sel?.card?.requires_coupon) {
          requires = true;
        }
      }

      if (requires) {
        const coupon = (pl.coupon_number || "").trim();
        if (!coupon || !isCompleteCoupon(coupon)) {
          return {
            valid: false,
            paymentline: pl,
            message: `El pago con ${method.name} requiere número de cupón válido (formato: 123-1234)`,
          };
        }
      }
    }

    return { valid: true };
  }

  // ✅ NUEVO: Formatear número de cupón (123-1234)
  function formatCoupon(raw) {
    const digits = String(raw || "")
      .replace(/\D/g, "")
      .slice(0, 7); // 3 + 4 dígitos
    if (digits.length <= 3) return digits;
    return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  }

  // ✅ NUEVO: Validar formato completo
  function isCompleteCoupon(value) {
    return /^\d{3}-\d{4}$/.test(String(value || ""));
  }

  patch(PaymentScreen.prototype, {
    setup() {
      const res = ORIGINAL.setup
        ? ORIGINAL.setup.apply(this, arguments)
        : undefined;
      ensureNumberKeyboardSound(this);
      setTimeout(() => recomputeTwice(this, null), 0);
      return res;
    },

    // ✅ Handler para cambio de tarjeta
    onPayAdjCardChange(ev) {
      const cardId = Number(ev?.target?.value || 0) || null;
      dlog("Card changed to:", cardId);

      const order = this.currentOrder;
      // Guardar a nivel línea (soporta pagos mixtos)
      const pl = getSelectedPaymentline(order, this) || getLastPaymentline(order, this);
      if (pl) {
        pl.__payAdjCardId = cardId;
      }
      // Guardamos también en la orden como fallback (compatibilidad)
      order.__payAdjSelectedCardId = cardId;

      // Resetear opción seleccionada al cambiar de tarjeta
      const method = resolveMethod(order, pl, this._payAdjCurrentMethod);
      if (method) {
        const card = findCard(method, cardId);
        const options = getCardOptions(card);
        if (options.length > 0) {
          const optId = options[0].id;
          if (pl) pl.__payAdjOptionId = optId;
          order.__payAdjSelectedOptionId = optId;
        }
      }

      recomputeTwice(this, null);
    },

    // ✅ Handler para cambio de opción (cuotas)
    onPayAdjOptionChange(ev) {
      const optionId = Number(ev?.target?.value || 0) || null;
      dlog("Option changed to:", optionId);
      const order = this.currentOrder;
      const pl = getSelectedPaymentline(order, this) || getLastPaymentline(order, this);
      if (pl) {
        pl.__payAdjOptionId = optionId;
      }
      order.__payAdjSelectedOptionId = optionId;
      recomputeTwice(this, null);
    },

    // ✅ NUEVO: Handler para input de cupón
    onPayAdjCouponInput(ev) {
      const raw = ev?.target?.value || "";
      const formatted = formatCoupon(raw);
      ev.target.value = formatted;

      const order = this.currentOrder;
      // Guardar solo en la línea seleccionada (pagos mixtos)
      const pl = getSelectedPaymentline(order, this) || getLastPaymentline(order, this);
      if (pl) {
        pl.coupon_number = formatted;
      }
    },

    // ✅ NUEVO: Handler para blur de cupón (validación)
    onPayAdjCouponBlur(ev) {
      const value = ev?.target?.value || "";
      const formatted = formatCoupon(value);
      ev.target.value = formatted;

      // Aplicar clase de validación visual
      if (formatted && !isCompleteCoupon(formatted)) {
        ev.target.classList.add("o_pos_coupon_input--error");
      } else {
        ev.target.classList.remove("o_pos_coupon_input--error");
      }
    },

    onCouponNumberInput(paymentline, ev) {
      const value = (ev?.target?.value || "").trim();
      paymentline.coupon_number = value;
    },

    get payAdjActive() {
      const o = this.currentOrder;
      const method = this._payAdjCurrentMethod;
      const cards = method ? getMethodCards(method) : [];
      const hasCards = cards.length > 0;

      // Mostrar la tarjeta si hay tarjetas para el método seleccionado,
      // o si hay ajuste activo (descuento o recargo total > 0)
      return !!o?.__payAdjActive || hasCards;
    },

    get payAdjType() {
      return this.currentOrder?.__payAdjType || "none";
    },

    get payAdjMethodName() {
      return this.currentOrder?.__payAdjMethodName || "";
    },

    // ✅ NUEVO: Verificar si tiene tarjetas
    get payAdjHasCards() {
      const method = this._payAdjCurrentMethod;
      const cards = method ? getMethodCards(method) : [];
      return cards.length > 0 && this.payAdjType === "surcharge";
    },

    // ✅ NUEVO: Obtener todas las tarjetas
    get payAdjCards() {
      const method = this._payAdjCurrentMethod;
      return method ? getMethodCards(method) : [];
    },

    // ✅ NUEVO: ID de tarjeta seleccionada
    get payAdjSelectedCardId() {
      const order = this.currentOrder;
      const pl = getSelectedPaymentline(order, this) || getLastPaymentline(order, this);
      return (
        Number(pl?.__payAdjCardId || order?.__payAdjSelectedCardId || 0) || null
      );
    },

    // ✅ NUEVO: Opciones solo de la tarjeta seleccionada
    get payAdjOptionsForSelectedCard() {
      const method = this._payAdjCurrentMethod;
      const cardId = this.payAdjSelectedCardId;
      if (!method || !cardId) return [];

      const card = findCard(method, cardId);
      return card ? getCardOptions(card) : [];
    },

    get payAdjSelectedOptionId() {
      const order = this.currentOrder;
      const pl = getSelectedPaymentline(order, this) || getLastPaymentline(order, this);
      return (
        Number(pl?.__payAdjOptionId || order?.__payAdjSelectedOptionId || 0) || null
      );
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
      const cardName = (o?.__payAdjSelectedCardName || "").trim();
      const optName = (o?.__payAdjSelectedOptionName || "").trim();

      if (t === "surcharge") {
        const parts = [];
        if (cardName) parts.push(cardName);
        if (optName) parts.push(optName);
        parts.push(`${pct}%`);
        return parts.join(" • ");
      }
      if (t === "discount") {
        return `${pct}%`;
      }
      return "";
    },

    // ✅ NUEVO: Detalle de cuotas (ej: "3 Cuotas de $20.10")
    get payAdjInstallmentDetail() {
      const o = this.currentOrder;
      if (o?.__payAdjType !== "surcharge") return "";

      const method = this._payAdjCurrentMethod;
      if (!method) return "";

      const cardId = this.payAdjSelectedCardId;
      const card = findCard(method, cardId);
      if (!card) return "";

      const optionId = this.payAdjSelectedOptionId;
      const option = findOption(card, optionId);
      if (!option) return "";

      const installments = Number(option.installments || 1);
      if (installments <= 1) return "";

      // En pagos mixtos mostramos el detalle de la línea seleccionada
      const pl = getSelectedPaymentline(o, this) || getLastPaymentline(o, this);
      const paid = pl ? getPaymentLineAmount(pl) : 0;
      if (!(paid > 0)) return "";

      const perInstallment = paid / installments;
      const formatted = formatCurrency(this, perInstallment);

      return `${installments} cuota${
        installments > 1 ? "s" : ""
      } de ${formatted}`;
    },

    // ✅ NUEVO: Verificar si la tarjeta requiere cupón
    get payAdjRequiresCoupon() {
      const method = this._payAdjCurrentMethod;
      if (!method) return false;

      const cardId = this.payAdjSelectedCardId;
      const card = findCard(method, cardId);

      return !!(card && card.requires_coupon);
    },

    // ✅ NUEVO: Obtener el número de cupón actual
    get payAdjCouponNumber() {
      const order = this.currentOrder;
      const pl = getSelectedPaymentline(order, this) || getLastPaymentline(order, this);
      return pl?.coupon_number || "";
    },

    get payAdjAmountFormatted() {
      const o = this.currentOrder;
      const amt = Number(o?.__payAdjAmount || 0);
      const t = o?.__payAdjType;

      if (amt === 0) {
        return `${formatCurrency(this, 0)}`;
      }

      const sign = t === "surcharge" ? "+" : "-";
      return `${sign} ${formatCurrency(this, amt)}`;
    },

    get _payAdjCurrentMethod() {
      const order = this.currentOrder;
      const selectedPl = getSelectedPaymentline(order, this);
      const selectedMethod = resolveMethod(order, selectedPl, null);
      if (selectedMethod) return selectedMethod;

      // Fallback: si todas las líneas usan el mismo método, devolverlo
      const pls = getPaymentlines(order, this);
      const methods = pls.map((pl) => resolveMethod(order, pl, null)).filter(Boolean);
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
        if (!pl.coupon_number) {
          pl.coupon_number = "";
        }

        // Si el método tiene tarjetas, inicializar la selección en la línea
        const method = paymentMethod || resolveMethod(this.currentOrder, pl, null);
        const cards = method ? getMethodCards(method) : [];
        if (cards.length) {
          pl.__payAdjCardId = cards[0].id;
          const opts = getCardOptions(cards[0]);
          if (opts.length) {
            pl.__payAdjOptionId = opts[0].id;
          }
          // fallback a nivel orden
          this.currentOrder.__payAdjSelectedCardId = pl.__payAdjCardId;
          this.currentOrder.__payAdjSelectedOptionId = pl.__payAdjOptionId || null;
        }
      }

      recomputeTwice(this, paymentMethod);
      return res;
    },

    deletePaymentLine() {
      const res = ORIGINAL.deletePaymentLine.apply(this, arguments);
      recomputeTwice(this, null);
      return res;
    },

    // Mantener el recargo actualizado al cambiar montos desde el keypad (si el core llama a estos métodos)
    updateSelectedPaymentline() {
      const res = ORIGINAL.updateSelectedPaymentline
        ? ORIGINAL.updateSelectedPaymentline.apply(this, arguments)
        : undefined;
      setTimeout(() => recompute(this, null), 0);
      return res;
    },

    selectPaymentLine() {
      const res = ORIGINAL.selectPaymentLine
        ? ORIGINAL.selectPaymentLine.apply(this, arguments)
        : undefined;
      setTimeout(() => recompute(this, null), 0);
      return res;
    },

    selectPaymentline() {
      const res = ORIGINAL.selectPaymentline
        ? ORIGINAL.selectPaymentline.apply(this, arguments)
        : undefined;
      setTimeout(() => recompute(this, null), 0);
      return res;
    },

    onKeypadInput() {
      ensureNumberKeyboardSound(this);
      const res = ORIGINAL.onKeypadInput
        ? ORIGINAL.onKeypadInput.apply(this, arguments)
        : undefined;
      setTimeout(() => recompute(this, null), 0);
      return res;
    },

    deleteOrderline(line) {
      if (line?.__payAdjLine || line?.__payAdjReadonly) {
        this.env.services.notification.add(
          _t(
            "Esta línea es un recargo automático y no se puede eliminar manualmente."
          ),
          { type: "warning" }
        );
        return;
      }

      if (ORIGINAL.deleteOrderline) {
        return ORIGINAL.deleteOrderline.apply(this, arguments);
      }
    },

    async validateOrder() {
      const order = this.currentOrder;
      if (!order) {
        return await ORIGINAL.validateOrder.apply(this, arguments);
      }

      // Asegurar que líneas de recargo y selección por paymentline estén al día
      await recompute(this, null);

      // Validación de cupones (por método y/o por tarjeta)
      const couponValidation = validateCouponNumbers(this);
      if (!couponValidation.valid) {
        // Intentar seleccionar la línea con error para que el input refleje el valor correcto
        if (couponValidation.paymentline) {
          trySelectPaymentline(this, couponValidation.paymentline);
        }

        this.env.services.notification.add(couponValidation.message, { type: "danger" });

        const input = document.querySelector(".o_pos_cash_discount_card__coupon_input");
        if (input) {
          input.classList.add("o_pos_coupon_input--error");
          input.focus();
        }
        return;
      }

      // Guardar información de tarjeta / plan por cada paymentline
      const pls = getPaymentlines(order, this);
      for (const pl of pls) {
        const method = resolveMethod(order, pl, null);
        if (!method) continue;

        const cards = getMethodCards(method);
        if (!cards.length) continue;

        const sel = ensureLineSelection(order, method, pl);
        const card = sel.card;
        const option = sel.option;
        if (!card || !option) continue;

        pl.card_name = card.name || "";
        pl.installments = Number(option.installments || 1);
        pl.installment_percent = Number(option.percent || 0);
        pl.installment_plan_name = option.name || "";
      }

      order.adjustment_type = order.__payAdjType || "none";
      order.adjustment_amount = Number(order.__payAdjAmount || 0);
      order.adjustment_percent = Number(order.__payAdjPercent || 0);

      return await ORIGINAL.validateOrder.apply(this, arguments);
    },
  });
}
