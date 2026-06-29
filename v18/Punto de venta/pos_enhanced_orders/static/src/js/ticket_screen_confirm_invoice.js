/** @odoo-module **/

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted, onPatched } from "@odoo/owl";

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

patch(TicketScreen.prototype, {
  setup() {
    super.setup(...arguments);
    onMounted(() => this._syncDraftInvoiceMainButtonLabel());
    onPatched(() => this._syncDraftInvoiceMainButtonLabel());
  },

  async onClickOrder(clickedOrder) {
    super.onClickOrder(clickedOrder);

    if (clickedOrder?.finalized) {
      await this._refreshOrderInvoiceState(clickedOrder);
    }
    this._syncDraftInvoiceMainButtonLabel();
  },

  async _refreshOrderInvoiceState(order) {
    if (!order?.id) return;

    const orm = this.env?.services?.orm || this.pos?.orm;
    if (!orm) return;

    try {
      const result = await orm.searchRead(
        "pos.order",
        [["id", "=", order.id]],
        ["invoice_state", "invoice_state_label", "account_move"],
        { limit: 1 },
      );

      if (result?.length > 0) {
        const fresh = result[0];
        order.invoice_state = fresh.invoice_state || "no_invoice";
        order.invoice_state_label = fresh.invoice_state_label || "Sin factura";
        order.account_move = fresh.account_move || false;
      }
    } catch (e) {
      console.warn("[REFRESH] Error:", e);
    }
  },

  _getSelectedPosOrder() {
    const uuid = this.state?.selectedOrderUuid;
    if (!uuid) return null;
    return this.pos.models["pos.order"]?.getBy?.("uuid", uuid) || null;
  },

  _shouldUseEmitDraftButton(order = null) {
    const selectedOrder = order || this._getSelectedPosOrder();
    if (!this.pos?.config?.show_ticket_btn_confirm_invoice) {
      return false;
    }
    return (selectedOrder?.invoice_state || "no_invoice") === "draft";
  },

  _findMainInvoiceButtons() {
    const root = this.el || document;
    return [...root.querySelectorAll("button")].filter((button) => {
      const text = normalizeText(button.textContent);
      return (
        text.includes("Recibo/Factura") ||
        text.includes("Reimprimir factura") ||
        text.includes("Emitir factura")
      );
    });
  },

  _syncDraftInvoiceMainButtonLabel() {
    const useEmitLabel = this._shouldUseEmitDraftButton();
    for (const button of this._findMainInvoiceButtons()) {
      if (!button.dataset.peoOriginalHtml) {
        button.dataset.peoOriginalHtml = button.innerHTML;
      }
      const originalHtml = button.dataset.peoOriginalHtml || button.innerHTML;
      if (useEmitLabel) {
        let replaced = originalHtml.replace(/Recibo\/Factura/gi, "Emitir factura");
        replaced = replaced.replace(/Reimprimir factura/gi, "Emitir factura");
        if (replaced === originalHtml) {
          replaced = originalHtml + " Emitir factura";
        }
        button.innerHTML = replaced;
      } else {
        button.innerHTML = originalHtml;
      }
    }
  },
});
