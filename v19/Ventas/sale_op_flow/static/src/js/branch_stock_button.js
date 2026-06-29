/** @odoo-module **/

/**
 * Botón "Ver stock en sucursales" para la línea de pedido.
 *
 * Se implementa como widget OWL (no como <button type="object"/action>) porque
 * esos botones fuerzan a guardar el pedido antes de ejecutarse. Este widget abre
 * el visor de stock del lado del cliente con doAction(), pasando el producto por
 * contexto, sin persistir la línea/pedido.
 */
import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

export class BranchStockButton extends Component {
    static template = "sale_op_flow.BranchStockButton";
    static props = { ...standardWidgetProps };

    setup() {
        this.action = useService("action");
    }

    get productId() {
        const val = this.props.record.data.product_id;
        if (!val) {
            return false;
        }
        if (Array.isArray(val)) {
            return val[0];
        }
        if (typeof val === "object") {
            return val.id || val.resId || false;
        }
        return val;
    }

    onClick() {
        const productId = this.productId;
        if (!productId) {
            return;
        }
        this.action.doAction("sale_op_flow.action_sof_product_branch_stock", {
            additionalContext: { default_product_id: productId, default_lock_product: true },
        });
    }
}

export const branchStockButton = {
    component: BranchStockButton,
};

registry.category("view_widgets").add("sof_branch_stock", branchStockButton);
