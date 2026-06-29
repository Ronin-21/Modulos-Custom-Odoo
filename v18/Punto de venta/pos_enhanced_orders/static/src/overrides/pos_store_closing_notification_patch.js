/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";

function getDraftInvoiceWizardClosingFlag() {
    return `pos.invoice_guard.draft_wizard.${odoo.pos_session_id}`;
}

patch(PosStore.prototype, {
    async closingSessionNotification(data) {
        if (localStorage.getItem(getDraftInvoiceWizardClosingFlag())) {
            return;
        }
        return super.closingSessionNotification(data);
    },
});
