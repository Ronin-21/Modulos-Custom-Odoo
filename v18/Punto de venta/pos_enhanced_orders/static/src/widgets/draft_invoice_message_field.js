/** @odoo-module */

import { Component, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";

class PosDraftInvoiceMessageField extends Component {
    static template = xml`
        <t t-if="hasError">
            <button type="button" class="btn btn-link p-0 o_pos_draft_invoice_message_btn" t-on-click="onClickError">
                <t t-esc="errorLabel"/>
            </button>
        </t>
        <t t-else="">
            <span class="o_pos_draft_invoice_message_text"><t t-esc="displayValue"/></span>
        </t>
    `;

    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.orm = useService("orm");
    }

    get hasError() {
        return Boolean(this.props.record.data.has_error_message);
    }

    get errorLabel() {
        return _t("Ver error");
    }

    get displayValue() {
        return this.props.record.data[this.props.name] || "";
    }

    async onClickError(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const action = await this.orm.call(
            this.props.record.resModel,
            "action_view_error",
            [[this.props.record.resId]]
        );
        if (!action) {
            return;
        }
        this.dialog.add(
            FormViewDialog,
            {
                resModel: action.res_model || action.resModel || "pos.draft.invoice.error.wizard",
                resId: action.res_id || action.resId,
                title: action.name || this.errorLabel,
                context: action.context || {},
            },
            {
                onClose: async () => {
                    await this.props.record.model.root.load();
                },
            }
        );
    }
}

registry.category("fields").add("pos_draft_invoice_message", {
    component: PosDraftInvoiceMessageField,
    supportedTypes: ["char", "text"],
});
