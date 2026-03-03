/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";
import { ActionService } from "@web/webclient/actions/action_service";
import { useService } from "@web/core/utils/hooks";
import { onMounted } from "@odoo/owl";

/**
 * Kiosk mode for Padron operators:
 * - Automatically opens the "Marcar Voto (Rápido)" wizard on login
 * - Hides navigation (home menu / navbar / control panel) so the user only uses the wizard search + mark
 */
patch(WebClient.prototype, {
    setup() {
        super.setup(...arguments);

        const actionService = useService("action");
        const userService = useService("user");

        onMounted(async () => {
            let isOperator = false;
            try {
                isOperator = await userService.hasGroup("padron_control.group_padron_operator");
            } catch (e) {
                // If something goes wrong, do nothing (avoid breaking the backend)
                return;
            }
            if (!isOperator) {
                return;
            }

            // Enable kiosk styling
            document.documentElement.classList.add("padron-operator-kiosk");

            // Prevent ESC from closing the wizard
            window.addEventListener(
                "keydown",
                (ev) => {
                    if (ev.key === "Escape") {
                        ev.preventDefault();
                        ev.stopPropagation();
                    }
                },
                true
            );

            // Open the quick vote wizard (modal)
            try {
                await actionService.doAction("padron_control.action_padron_quick_vote_wizard");
            } catch (e) {
                // ignore
            }
        });
    },
});

// Extra safety: even if the operator tries to navigate to another menu/action (URL manipulation,
// browser history, etc.), force the Quick Vote wizard.
const KIOSK_WIZARD_XMLID = "padron_control.action_padron_quick_vote_wizard";
let _kioskEnabledPromise = null;
let _kioskRedirecting = false;

async function isKioskUser(env) {
    if (!_kioskEnabledPromise) {
        _kioskEnabledPromise = env.services.user
            .hasGroup("padron_control.group_padron_operator")
            .catch(() => false);
    }
    return await _kioskEnabledPromise;
}

function isWizardAction(actionRequest) {
    if (!actionRequest) {
        return false;
    }
    if (typeof actionRequest === "string") {
        return actionRequest === KIOSK_WIZARD_XMLID;
    }
    // Some callers pass the resolved action dict
    if (actionRequest.xml_id) {
        return actionRequest.xml_id === KIOSK_WIZARD_XMLID;
    }
    if (actionRequest.res_model) {
        return actionRequest.res_model === "padron.quick.vote.wizard";
    }
    return false;
}

patch(ActionService.prototype, {
    async doAction(actionRequest, options = {}) {
        if (_kioskRedirecting) {
            return await super.doAction(actionRequest, options);
        }

        if (await isKioskUser(this.env)) {
            // Allow only the kiosk wizard. Everything else is redirected to it.
            if (!isWizardAction(actionRequest)) {
                _kioskRedirecting = true;
                try {
                    return await super.doAction(KIOSK_WIZARD_XMLID, {
                        ...options,
                        clearBreadcrumbs: true,
                    });
                } finally {
                    _kioskRedirecting = false;
                }
            }
        }

        return await super.doAction(actionRequest, options);
    },
});
