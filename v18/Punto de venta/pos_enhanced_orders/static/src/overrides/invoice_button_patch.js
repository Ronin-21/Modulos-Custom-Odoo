/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { InvoiceButton } from "@point_of_sale/app/screens/ticket_screen/invoice_button/invoice_button";
import { ask, makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { onMounted, onPatched } from "@odoo/owl";

patch(InvoiceButton.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => this._syncEmitDraftButtonLabel());
        onPatched(() => this._syncEmitDraftButtonLabel());
    },

    _getInvoiceButtonElement() {
        if (!this.el) {
            return null;
        }
        return this.el.matches?.("button") ? this.el : this.el.querySelector?.("button") || this.el;
    },

    _syncEmitDraftButtonLabel() {
        const button = this._getInvoiceButtonElement();
        if (!button) {
            return;
        }
        if (!button.dataset.peoOriginalHtml) {
            button.dataset.peoOriginalHtml = button.innerHTML;
        }
        const useEmitLabel = this._shouldEmitDraftInvoice(this.props?.order);
        const originalHtml = button.dataset.peoOriginalHtml || button.innerHTML;
        if (!useEmitLabel) {
            button.innerHTML = originalHtml;
            return;
        }
        let replaced = originalHtml.replace(/Recibo\/Factura/gi, "Emitir factura");
        replaced = replaced.replace(/Reimprimir factura/gi, "Emitir factura");
        if (replaced === originalHtml) {
            replaced = originalHtml + " Emitir factura";
        }
        button.innerHTML = replaced;
    },

    async _refreshLocalOrderState(orderId) {
        const orm = this.env?.services?.orm;
        if (!orm) {
            return null;
        }
        const result = await orm.searchRead(
            "pos.order",
            [["id", "=", orderId]],
            ["invoice_state", "invoice_state_label", "account_move"],
            { limit: 1 },
        );
        const fresh = result?.[0] || null;
        const localOrder = this.pos.models["pos.order"].get(orderId) || this.props.order;
        if (fresh && localOrder) {
            localOrder.invoice_state = fresh.invoice_state || "no_invoice";
            localOrder.invoice_state_label = fresh.invoice_state_label || "Sin factura";
            localOrder.account_move = fresh.account_move || false;
            if (localOrder.raw) {
                localOrder.raw.account_move = fresh.account_move || false;
            }
        }
        return fresh;
    },

    async _tryPrintEticketInvoice(orderId) {
        try {
            await this.pos.data.read("pos.order", [orderId], [], { load: false });
            const order = this.pos.models["pos.order"].get(orderId) || this.props.order;
            const accountMoveId = order?.raw?.account_move;
            if (!order || !accountMoveId) {
                return false;
            }
            const moveVals = await this.pos.data.call("account.move", "get_move_vals", [accountMoveId]);
            if (!moveVals || typeof moveVals !== "object" || !moveVals.invoice_id) {
                return false;
            }
            order.move_vals = moveVals;
            order.raw.account_move = accountMoveId;
            if (this.props.order && this.props.order.id === order.id) {
                this.props.order.move_vals = moveVals;
                this.props.order.raw.account_move = accountMoveId;
            }
            await this.pos.printReceipt({ order });
            return true;
        } catch {
            return false;
        }
    },

    _shouldEmitDraftInvoice(order) {
        return Boolean(
            this.pos?.config?.show_ticket_btn_confirm_invoice &&
            order &&
            (order.invoice_state || "no_invoice") === "draft"
        );
    },

    async _emitDraftInvoice(orderId) {
        const orm = this.env?.services?.orm;
        if (!orm) {
            this.dialog.add(AlertDialog, {
                title: _t("Error"),
                body: _t("No se pudo conectar al servidor."),
            });
            return;
        }

        const res = await orm.call("pos.order", "pos_fiscal_post_from_pos", [orderId]);
        await this._refreshLocalOrderState(orderId);
        this.props.onInvoiceOrder(orderId);

        this.dialog.add(AlertDialog, {
            title: _t("Factura emitida"),
            body: res?.note || _t("La factura fue emitida. La conciliación o el pago quedan para un paso posterior."),
        });
    },

    async _invoiceOrder() {
        const order = this.props.order;
        if (!order) {
            return;
        }

        const orderId = order.id;
        await this._refreshLocalOrderState(orderId);

        if (this._shouldEmitDraftInvoice(order)) {
            await this._emitDraftInvoice(orderId);
            return;
        }

        if (this.isAlreadyInvoiced) {
            const printedEticket = await this._tryPrintEticketInvoice(orderId);
            if (!printedEticket) {
                await this._downloadInvoice(orderId);
            }
            this.props.onInvoiceOrder(orderId);
            return;
        }

        let partner = order.get_partner();
        if (!partner) {
            const confirmed = await ask(this.dialog, {
                title: _t("Hace falta un cliente para facturar"),
                body: _t("¿Quiere abrir la lista de clientes para elegir uno?"),
            });
            if (!confirmed) {
                return;
            }
            partner = await makeAwaitable(this.dialog, PartnerList);
            if (!partner) {
                return;
            }
            await this.pos.data.ormWrite("pos.order", [orderId], { partner_id: partner.id });
        }

        const validated = await this.onWillInvoiceOrder(order, partner);
        if (!validated) {
            return;
        }

        await this.pos.data.call("pos.order", "action_pos_order_invoice", [orderId]);
        const printedEticket = await this._tryPrintEticketInvoice(orderId);
        if (!printedEticket) {
            await this._downloadInvoice(orderId);
        }
        this.props.onInvoiceOrder(orderId);
    },
});
