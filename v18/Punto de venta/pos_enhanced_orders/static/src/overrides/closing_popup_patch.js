/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

function getDraftInvoiceWizardClosingFlag() {
    return `pos.invoice_guard.draft_wizard.${odoo.pos_session_id}`;
}

patch(ClosePosPopup.prototype, {
    async handleClosingError(response) {
        if (response?.type === "alert") {
            this.dialog.add(AlertDialog, {
                title: response.title || _t("Error"),
                body: response.message,
            });
            if (response.redirect) {
                window.location.reload();
            }
            return;
        }

        if (response?.type === "draft_invoice_confirmation" && response?.wizard_id) {
            localStorage.setItem(getDraftInvoiceWizardClosingFlag(), "1");
            this.dialog.add(
                FormViewDialog,
                {
                    resModel: response.wizard_model || "pos.draft.invoice.confirmation.wizard",
                    resId: response.wizard_id,
                    title: response.title,
                    context: {
                        login_number: odoo.login_number,
                    },
                },
                {
                    onClose: async () => {
                        const session = await this.pos.data.read("pos.session", [this.pos.session.id]);
                        if (session[0] && session[0].state === "closed") {
                            localStorage.removeItem(`pos.session.${odoo.pos_config_id}`);
                            location.reload();
                            return;
                        }
                        localStorage.removeItem(getDraftInvoiceWizardClosingFlag());
                    },
                }
            );
            return;
        }
        return super.handleClosingError(...arguments);
    },
});
