/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

// Odoo 18 suele tener Action Pad en action_pad/action_pad (nombres con guión bajo).
// En algunas ramas/custom builds puede variar; este import es el correcto para Odoo 18 estándar.
import { ActionpadWidget } from "@point_of_sale/app/screens/product_screen/action_pad/action_pad";

/**
 * Botón visible en la pantalla principal (Action Pad) para reenviar comanda.
 * Reimprime la última comanda generada para cada impresora de preparación,
 * guardada en order.__last_prep_prints por el patch del PosStore.
 */
patch(ActionpadWidget.prototype, {
    async onClickResendPreparationComanda() {
        const order = this.pos.get_order();
        const prints = order?.__last_prep_prints || {};
        if (!order || !Object.keys(prints).length) {
            this.env.services.notification.add(
                _t("No hay una comanda previa para reenviar en esta orden."),
                { type: "warning" }
            );
            return;
        }

        const res = await this.pos.resendLastPreparationReceipts(order);

        if (res.failed || res.missing) {
            this.env.services.notification.add(
                _t(`Comanda reenviada. OK: ${res.printed}, Fallidas: ${res.failed}, Omitidas: ${res.missing}`),
                { type: "warning" }
            );
        } else {
            this.env.services.notification.add(_t("Comanda reenviada."), { type: "success" });
        }
    },
});
