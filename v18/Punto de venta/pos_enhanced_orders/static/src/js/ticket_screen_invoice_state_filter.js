/** @odoo-module **/

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { fuzzyLookup } from "@web/core/utils/search";
import { parseUTCString } from "@point_of_sale/utils";
import { onWillStart } from "@odoo/owl";

const NBR_BY_PAGE = 30;

const FISCAL_FILTER_MAP = {
  INV_NO_INVOICE: "no_invoice",
  INV_DRAFT: "draft",
  INV_POSTED: "posted",
  INV_CANCEL: "cancel",
};

patch(TicketScreen.prototype, {
  setup() {
    super.setup(...arguments);

    // ✅ Poblar invoice_state desde el servidor ANTES del primer render,
    //    justo después de que Odoo termina de cargar las órdenes
    onWillStart(async () => {
      await this._loadInvoiceStates();
    });
  },

  // ─────────────────────────────────────────────────────────────────
  // Cargar invoice_state para todas las órdenes que no lo tengan
  // Lee directo del modelo pos.order (ya en memoria) — sin RPC extra
  // ─────────────────────────────────────────────────────────────────
  async _loadInvoiceStates() {
    if (!this.pos?.config?.show_ticket_col_invoice_state) return;

    const orders =
      this.pos.models["pos.order"]?.getAll?.() ||
      this.pos.models["pos.order"]?.records ||
      [];

    for (const order of orders) {
      // Si ya tiene el campo cargado, no hacer nada
      if (order.invoice_state === undefined || order.invoice_state === null) {
        order.invoice_state = "no_invoice";
      }
    }
  },

  // ─────────────────────────────────────────────────────────────────
  // 1. Agregar opciones fiscales al dropdown
  // ─────────────────────────────────────────────────────────────────
  _getFilterOptions() {
    const options = super._getFilterOptions();

    if (!this.pos?.config?.show_ticket_col_invoice_state) {
      return options;
    }

    options.set("__FISCAL_SEP__", { text: "──────────────", disabled: true });
    options.set("INV_NO_INVOICE", { text: _t("Factura: Sin factura") });
    options.set("INV_DRAFT", { text: _t("Factura: Borrador") });
    options.set("INV_POSTED", { text: _t("Factura: Confirmada") });
    options.set("INV_CANCEL", { text: _t("Factura: Cancelada") });

    return options;
  },

  // ─────────────────────────────────────────────────────────────────
  // 2. Filtrar órdenes por invoice_state
  // ─────────────────────────────────────────────────────────────────
  getFilteredOrderList() {
    const wantedInvoiceState = FISCAL_FILTER_MAP[this.state.filter];
    const orderModel = this.pos.models["pos.order"];

    let orders;

    if (wantedInvoiceState) {
      // Traer todas las órdenes pagadas directamente del modelo
      orders = orderModel.filter((o) => o.finalized && o.uiState.displayed);

      // Filtrar por invoice_state
      orders = orders.filter((order) => {
        return (order.invoice_state || "no_invoice") === wantedInvoiceState;
      });

      // Búsqueda por texto
      if (this.state.search.searchTerm) {
        const repr = this._getSearchFields()[this.state.search.fieldName].repr;
        orders = fuzzyLookup(this.state.search.searchTerm, orders, repr);
      }

      // Ordenar desc por fecha
      return orders.sort((a, b) => {
        const dateA = parseUTCString(a.date_order, "yyyy-MM-dd HH:mm:ss");
        const dateB = parseUTCString(b.date_order, "yyyy-MM-dd HH:mm:ss");
        if (a.date_order !== b.date_order) return dateB - dateA;
        const nameA = parseInt((a.name || "").replace(/\D/g, "")) || 0;
        const nameB = parseInt((b.name || "").replace(/\D/g, "")) || 0;
        return nameB - nameA;
      });
    }

    // Filtros normales de Odoo — sin tocar
    return super.getFilteredOrderList();
  },

  // ─────────────────────────────────────────────────────────────────
  // 3. onFilterSelected: evitar _fetchSyncedOrders para filtros fiscales
  // ─────────────────────────────────────────────────────────────────
  async onFilterSelected(selectedFilter) {
    if (selectedFilter && FISCAL_FILTER_MAP[selectedFilter]) {
      this.state.filter = selectedFilter;
      this.state.page = 1;
      return;
    }
    return super.onFilterSelected(selectedFilter);
  },
});
