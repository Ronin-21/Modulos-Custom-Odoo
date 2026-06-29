/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ConnectionLostError, RPCError } from "@web/core/network/rpc";
import { serializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { odooExceptionTitleMap } from "@web/core/errors/error_dialogs";

function extractRpcErrorBody(error) {
    return (
        error?.data?.debug?.status?.message_body ||
        error?.data?.message ||
        error?.data?.arguments?.[0] ||
        error?.message ||
        _t("El servidor devolvió un error al recibir la orden.")
    );
}

function extractRpcErrorTitle(error) {
    if (error?.exceptionName && odooExceptionTitleMap.has(error.exceptionName)) {
        return odooExceptionTitleMap.get(error.exceptionName).toString();
    }
    return _t("No se pudo validar la orden");
}

patch(PaymentScreen.prototype, {
    _showDetailedRpcValidationError(error) {
        this.dialog.add(AlertDialog, {
            title: extractRpcErrorTitle(error),
            body: extractRpcErrorBody(error),
        });
    },

    async _loadInvoiceMoveValsIfAvailable() {
        const accountMoveId = this.currentOrder?.raw?.account_move;
        if (!accountMoveId) {
            return;
        }
        try {
            const moveVals = await this.pos.data.call("account.move", "get_move_vals", [accountMoveId]);
            if (moveVals && typeof moveVals === "object") {
                this.currentOrder.move_vals = moveVals;
            }
        } catch {
            // Método opcional usado por módulos como l10n_ar_pos_eticket.
        }
    },

    async _finalizeValidation() {
        if (this.currentOrder.is_paid_with_cash() || this.currentOrder.get_change()) {
            this.hardwareProxy.openCashbox();
        }

        this.currentOrder.date_order = serializeDateTime(luxon.DateTime.now());
        for (const line of this.paymentLines) {
            if (!line.amount === 0) {
                this.currentOrder.remove_paymentline(line);
            }
        }

        this.pos.addPendingOrder([this.currentOrder.id]);
        this.currentOrder.state = "paid";

        this.env.services.ui.block();
        let syncOrderResult;
        try {
            syncOrderResult = await this.pos.syncAllOrders({ throw: true });
            if (!syncOrderResult) {
                return;
            }

            if (this.shouldDownloadInvoice() && this.currentOrder.is_to_invoice()) {
                if (this.currentOrder.raw.account_move) {
                    await this.invoiceService.downloadPdf(this.currentOrder.raw.account_move);
                } else {
                    this.dialog.add(AlertDialog, {
                        title: _t("Factura no emitida"),
                        body: _t(
                            "La orden se sincronizó, pero el backend no devolvió una factura. Revísela desde el backend antes de seguir."
                        ),
                    });
                    return false;
                }
            }

            await this._loadInvoiceMoveValsIfAvailable();
        } catch (error) {
            if (error instanceof ConnectionLostError) {
                if (this.currentOrder.is_to_invoice()) {
                    this.currentOrder.state = "draft";
                    this.pos.removePendingOrder(this.currentOrder);
                    this.dialog.add(AlertDialog, {
                        title: _t("Factura requerida"),
                        body: _t(
                            "La orden no se validó porque requiere factura y se perdió la conexión con el servidor."
                        ),
                    });
                    return error;
                }
                this.afterOrderValidation();
                Promise.reject(error);
            } else if (error instanceof RPCError) {
                this.currentOrder.state = "draft";
                this.pos.removePendingOrder(this.currentOrder);
                this._showDetailedRpcValidationError(error);
            } else if (error?.message === "Backend Invoice") {
                this.dialog.add(AlertDialog, {
                    title: _t("Factura no emitida"),
                    body: _t(
                        "La orden se sincronizó, pero el backend no devolvió una factura. Revísela desde el backend."
                    ),
                });
            } else {
                throw error;
            }
            return error;
        } finally {
            this.env.services.ui.unblock();
        }

        const postPushOrders = syncOrderResult.filter((order) => order.wait_for_push_order());
        if (postPushOrders.length > 0) {
            await this.postPushOrderResolve(postPushOrders.map((order) => order.id));
        }

        await this.afterOrderValidation(!!syncOrderResult && syncOrderResult.length > 0);
    },
});
