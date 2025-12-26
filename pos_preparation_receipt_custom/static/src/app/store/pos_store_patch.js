import { patch } from "@web/core/utils/patch";
import { renderToElement } from "@web/core/utils/render";
import { PosStore } from "@point_of_sale/app/store/pos_store";

/**
 * Agrega datos extra al contexto de impresión de la comanda (Impresoras de preparación).
 *
 * Objetivos:
 *  - Mostrar Mozo responsable (waiter_name).
 *  - Mostrar Nombre de la impresora de preparación.
 *  - Mantener compatibilidad y no romper POSs donde no existan esos campos.
 */
patch(PosStore.prototype, {
    getPrintingChanges(order, diningModeUpdate) {
        const changes = super.getPrintingChanges(order, diningModeUpdate);

        // Salón / Piso (según cómo venga table_id)
        changes.floor_name =
            order?.table_id?.floor?.name ||
            order?.table_id?.floor_id?.name ||
            "";

        // UID corto (útil cuando no hay tracking_number)
        const uid = order?.uid || "";
        changes.order_uid_short = uid ? uid.slice(-6) : "";

        // Mozo responsable (campo custom en pos.order o equivalente)
        changes.waiter_name =
            order?.waiter_name ||
            order?.waiter?.name ||
            order?.waiter_id?.name ||
            "";

        return changes;
    },

    /**
     * Necesitamos conocer la impresora para imprimir su nombre en la comanda.
     * El core no pasa "printer" al template, así que lo inyectamos acá.
     */
    async printReceipts(order, printer, title, lines, fullReceipt = false, diningModeUpdate) {
        const changes = this.getPrintingChanges(order, diningModeUpdate);

        // Nombre de la impresora (según cómo venga el objeto)
        changes.printer_name =
            printer?.name ||
            printer?.printer_name ||
            printer?.config?.name ||
            "";

        const receipt = renderToElement("point_of_sale.OrderChangeReceipt", {
            operational_title: title,
            changes: changes,
            changedlines: lines,
            fullReceipt: fullReceipt,
        });

        const result = await printer.printReceipt(receipt);
        return result.successful;
    },
});
