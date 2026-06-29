/** @odoo-module */

import { Component, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

class PosDraftInvoiceActionsField extends Component {
    static template = xml`
        <div class="o_pos_draft_invoice_actions">
            <button t-if="canView" type="button" class="btn btn-link btn-sm o_pos_draft_invoice_action_btn" t-on-click="onClickView">
                <t t-esc="viewLabel"/>
            </button>
            <button t-if="canEmit" type="button" class="btn btn-primary btn-sm o_pos_draft_invoice_action_btn" t-on-click="onClickEmit">
                <t t-esc="emitLabel"/>
            </button>
            <button t-if="canPay" type="button" class="btn btn-primary btn-sm o_pos_draft_invoice_action_btn" t-on-click="onClickPay">
                <t t-esc="payLabel"/>
            </button>
            <button t-if="canDelete" type="button" class="btn btn-danger btn-sm o_pos_draft_invoice_action_btn o_pos_draft_invoice_action_btn_delete" t-on-click="onClickDelete" aria-label="Eliminar" title="Eliminar">
                <span class="o_pos_draft_invoice_action_close">X</span>
            </button>
        </div>
    `;

    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.orm = useService("orm");
    }

    get canView() {
        return Boolean(this.props.record.data.can_view);
    }

    get canEmit() {
        return Boolean(this.props.record.data.can_emit);
    }

    get canPay() {
        return Boolean(this.props.record.data.can_pay);
    }

    get canDelete() {
        return Boolean(this.props.record.data.can_delete);
    }

    get viewLabel() {
        return _t("Ver");
    }

    get emitLabel() {
        return _t("Emitir");
    }

    get payLabel() {
        return this.props.record.data.payment_action_label || _t("Pagar");
    }

    async _reloadRoot() {
        await this.props.record.model.root.load();
    }

    async onClickView(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const action = await this.orm.call(
            this.props.record.resModel,
            "action_view_order",
            [[this.props.record.resId]]
        );
        if (action) {
            await this.action.doAction(action, {
                onClose: async () => {
                    await this._reloadRoot();
                },
            });
        }
    }

    async onClickEmit(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        await this.orm.call(this.props.record.resModel, "action_emit_invoice", [[this.props.record.resId]]);
        await this._reloadRoot();
    }

    async onClickPay(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const action = await this.orm.call(this.props.record.resModel, "action_pay_invoice", [[this.props.record.resId]]);
        if (action) {
            await this.action.doAction(action, {
                onClose: async () => {
                    await this._reloadRoot();
                },
            });
        } else {
            await this._reloadRoot();
        }
    }

    async onClickDelete(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.dialog.add(ConfirmationDialog, {
            title: _t("Eliminar factura borrador"),
            body: _t(
                "Esta operación no se puede deshacer. ¿Quiere eliminar la factura borrador y sus asientos de pago del POS relacionados?"
            ),
            confirmLabel: _t("Eliminar"),
            cancelLabel: _t("Cancelar"),
            confirm: async () => {
                await this.orm.call(
                    this.props.record.resModel,
                    "action_delete_draft_invoice",
                    [[this.props.record.resId]]
                );
                await this._reloadRoot();
            },
        });
    }
}

registry.category("fields").add("pos_draft_invoice_actions", {
    component: PosDraftInvoiceActionsField,
    supportedTypes: ["char", "text"],
});
