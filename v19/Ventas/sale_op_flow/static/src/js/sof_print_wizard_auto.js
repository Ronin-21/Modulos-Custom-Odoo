/** @odoo-module **/
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { useService } from "@web/core/utils/hooks";
import { useEffect } from "@odoo/owl";

class SofPrintWizardController extends FormController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
        useEffect(
            () => {
                const root = this.model.root;
                if (root.data?.auto_print && root.resId) {
                    setTimeout(async () => {
                        const action = await this.orm.call(
                            "sof.print.wizard",
                            "action_print_invoice",
                            [[root.resId]],
                            {}
                        );
                        // Cerrar el dialog antes de descargar para no mostrar el wizard durante la generación del PDF
                        await this.actionService.doAction({
                            type: "ir.actions.act_window_close",
                        });
                        await this.actionService.doAction(action);
                    }, 0);
                }
            },
            () => [this.model.root.resId]
        );
    }
}

registry.category("views").add("sof_print_wizard_form", {
    ...formView,
    Controller: SofPrintWizardController,
});
