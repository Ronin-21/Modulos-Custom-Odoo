/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ActionpadWidget } from "@point_of_sale/app/screens/product_screen/action_pad/action_pad";
import { renderToElement } from "@web/core/utils/render";

patch(ActionpadWidget.prototype, {
  setup() {
    super.setup();
    const services = (this.env && this.env.services) || {};
    this._popup = services["popup"] || null;
    this._notification = services["notification"] || null;
    this._pos = this.pos || services["pos"] || null;
    this._printer = services["pos_printer"] || services["printer"] || null;
  },

  get showOrderTicketButton() {
    const pos = this._pos || this.pos || this.env?.services?.["pos"];
    return Boolean(pos?.config?.enable_order_ticket);
  },

  async _showError(title, body) {
    if (this._popup?.add) {
      await this._popup.add("ErrorPopup", { title, body });
      return;
    }
    if (this._notification?.add) {
      this._notification.add(body, { title, type: "danger" });
      return;
    }
    window.alert(`${title}\n\n${body}`);
  },

  _formatQty(qty) {
    const n = Number(qty || 0);
    return Number.isInteger(n) ? String(n) : n.toFixed(2);
  },

  async onClickOrderTicket() {
    const pos = this._pos || this.pos || this.env?.services?.["pos"];
    const order = pos?.get_order?.();
    const orderlines = order?.get_orderlines?.() || [];

    if (!order || !orderlines.length) {
      await this._showError(
        "Sin productos",
        "Agregá al menos un producto para imprimir el ticket de pedido.",
      );
      return;
    }

    order.uiState = order.uiState || {};
    const reprint = Boolean(order.uiState.order_ticket_printed);

    const lines = orderlines.map((line) => {
      const product =
        (typeof line.get_product === "function" && line.get_product()) ||
        line.product;
      const name = product?.display_name || product?.name || "";

      const qty =
        typeof line.get_quantity === "function"
          ? line.get_quantity()
          : (line.quantity ?? line.qty ?? 0);

      const note =
        typeof line.get_note === "function"
          ? line.get_note()
          : (line.note ?? line.customer_note ?? "");

      return {
        name,
        qty: Number.isInteger(qty) ? String(qty) : Number(qty || 0).toFixed(2),
        note,
      };
    });

    const header = {
      order_name: order.name || order.uid || "",
      cashier: pos?.get_cashier?.()?.name || "",
      partner: order.get_partner?.()?.name || "",
      date: new Date().toLocaleString(),
    };

    const receiptEl = renderToElement("pos_order_ticket.OrderTicketReceipt", {
      header,
      lines,
      reprint,
    });

    try {
      const printer = this._printer;

      if (printer?.printReceipt) {
        await printer.printReceipt(receiptEl);
      } else if (printer?.printHtml) {
        await printer.printHtml(receiptEl);
      } else {
        const w = window.open("", "_blank");
        w.document.open();
        w.document.write(
          `<html><head><title>Pedido</title></head><body>${receiptEl.outerHTML}</body></html>`,
        );
        w.document.close();
        w.focus();
        w.print();
        w.close();
      }

      order.uiState.order_ticket_printed = true;
    } catch (e) {
      await this._showError(
        "Error al imprimir",
        e?.message || "No se pudo imprimir el ticket.",
      );
    }
  },
});
