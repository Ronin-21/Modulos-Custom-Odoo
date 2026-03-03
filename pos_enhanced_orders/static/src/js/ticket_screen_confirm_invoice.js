/** @odoo-module **/

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

patch(TicketScreen.prototype, {
  // ========================================================================
  // REFRESH al hacer click en orden
  // ========================================================================
  async onClickOrder(clickedOrder) {
    super.onClickOrder(clickedOrder);

    if (clickedOrder?.finalized) {
      await this._refreshOrderInvoiceState(clickedOrder);
    }
  },

  async _refreshOrderInvoiceState(order) {
    if (!order?.id) return;

    const orm = this.env?.services?.orm || this.pos?.orm;
    if (!orm) return;

    try {
      console.log("[REFRESH] Refreshing:", order.pos_reference);

      const result = await orm.searchRead(
        "pos.order",
        [["id", "=", order.id]],
        ["invoice_state", "invoice_state_label", "account_move"],
        { limit: 1 },
      );

      if (result?.length > 0) {
        const fresh = result[0];
        const oldState = order.invoice_state;

        order.invoice_state = fresh.invoice_state || "no_invoice";
        order.invoice_state_label = fresh.invoice_state_label || "Sin factura";
        order.account_move = fresh.account_move || false;

        console.log("[REFRESH] Updated:", oldState, "→", order.invoice_state);

        // ✅ SOLUCIÓN: Cambiar algo en this.state para disparar onPatched
        // que a su vez dispara el re-render de las columnas DOM
        const currentPage = this.state.page;
        this.state.page = currentPage + 0.0001; // Cambio mínimo que dispara reactivity
        await new Promise((resolve) => setTimeout(resolve, 0));
        this.state.page = currentPage; // Restaurar
      }
    } catch (e) {
      console.warn("[REFRESH] Error:", e);
    }
  },

  // ========================================================================
  // Mostrar botón solo si está habilitado y hay factura draft
  // ========================================================================
  selectedOrderHasDraftInvoice() {
    if (!this.pos?.config?.show_ticket_btn_confirm_invoice) {
      return false;
    }

    const uuid = this.state?.selectedOrderUuid;
    if (!uuid) return false;

    const order = this.pos.models["pos.order"]?.getBy?.("uuid", uuid);
    if (!order) return false;

    return (order.invoice_state || "no_invoice") === "draft";
  },

  // ========================================================================
  // CONFIRMAR FACTURA + INTENTAR CONCILIAR (VIA BACKEND)
  // ========================================================================
  async onConfirmDraftInvoice() {
    const order = this.getSelectedOrder();
    if (!order) return;

    const orm = this.env?.services?.orm || this.pos?.orm;
    if (!orm) {
      this.dialog.add(AlertDialog, {
        title: _t("Error"),
        body: _t("No se pudo conectar al servidor."),
      });
      return;
    }

    try {
      console.log("=== CONFIRMAR FACTURA: INICIO ===");

      // PASO 1: Refrescar estado
      console.log("[STEP 1] Refreshing...");
      const freshData = await orm.searchRead(
        "pos.order",
        [["id", "=", order.id]],
        ["invoice_state", "invoice_state_label", "account_move"],
        { limit: 1 },
      );

      if (!freshData?.length) {
        throw new Error("No se pudo leer la orden");
      }

      const fresh = freshData[0];
      order.invoice_state = fresh.invoice_state || "no_invoice";
      order.invoice_state_label = fresh.invoice_state_label || "Sin factura";
      order.account_move = fresh.account_move || false;

      console.log("[STEP 1] State:", order.invoice_state);

      // PASO 2: Validar
      if (order.invoice_state === "posted") {
        this.dialog.add(AlertDialog, {
          title: _t("Ya confirmada"),
          body: _t("Esta factura ya está confirmada."),
        });
        // Forzar refresh visual
        this.state.page = this.state.page + 0.0001;
        await new Promise((r) => setTimeout(r, 0));
        this.state.page = Math.round(this.state.page);
        return;
      }

      if (order.invoice_state !== "draft") {
        this.dialog.add(AlertDialog, {
          title: _t("No es borrador"),
          body: _t("Estado: ") + (order.invoice_state || "no_invoice"),
        });
        this.state.page = this.state.page + 0.0001;
        await new Promise((r) => setTimeout(r, 0));
        this.state.page = Math.round(this.state.page);
        return;
      }

      // PASO 3: Backend post + reconcile
      console.log("[STEP 2] Backend post + reconcile...");
      const res = await orm.call(
        "pos.order",
        "pos_fiscal_post_and_reconcile_from_pos",
        [order.id],
      );
      console.log("[STEP 2] Backend result:", res);

      // PASO 4: Refrescar UI
      console.log("[STEP 3] Refreshing after backend...");
      await this._refreshOrderInvoiceState(order);

      // PASO 5: Mensaje final
      const residual = res?.amount_residual ?? null;
      const reconciled = !!res?.reconciled;
      const note = res?.note ? String(res.note) : "";

      if (reconciled || (residual !== null && residual <= 0)) {
        this.dialog.add(AlertDialog, {
          title: _t("Factura confirmada"),
          body: _t("La factura fue confirmada y quedó pagada."),
        });
      } else {
        if (note) {
          this.dialog.add(AlertDialog, {
            title: _t("Factura confirmada"),
            body: note,
          });
        } else {
          this.dialog.add(AlertDialog, {
            title: _t("Factura confirmada"),
            body:
              _t("La factura fue confirmada, pero quedó saldo pendiente: ") +
              String(residual),
          });
        }
      }

      console.log("=== SUCCESS ===");
    } catch (e) {
      console.error("=== ERROR ===");
      console.error(e);

      this.dialog.add(AlertDialog, {
        title: _t("Error"),
        body: _t("Error: ") + (e?.data?.message || e?.message || String(e)),
      });
    }
  },
});
