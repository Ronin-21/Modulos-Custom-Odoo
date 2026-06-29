/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";

function mccIsPosAvailable(partner) {
    if (!partner) {
        return false;
    }
    const raw = partner.raw || partner;
    const value = partner.mcc_effective_pos_available ?? raw.mcc_effective_pos_available;
    return value === true;
}

function mccPosDomain() {
    return [["mcc_effective_pos_available", "=", true]];
}

patch(PartnerList.prototype, {
    getPartners() {
        const partners = super.getPartners(...arguments) || [];
        return partners.filter((partner) => mccIsPosAvailable(partner));
    },

    async getNewPartners() {
        let domain = mccPosDomain();
        const limit = 30;

        if (this.state.query) {
            const searchFields = [
                "name",
                "parent_name",
                ...this.getPhoneSearchTerms(),
                "email",
                "barcode",
                "street",
                "zip",
                "city",
                "state_id",
                "country_id",
                "vat",
            ];
            const searchDomain = [
                ...Array(searchFields.length - 1).fill("|"),
                ...searchFields.map((field) => [field, "ilike", this.state.query + "%"]),
            ];
            domain = ["&", ["mcc_effective_pos_available", "=", true], ...searchDomain];
        }

        const result = await this.pos.data.searchRead("res.partner", domain, [], {
            limit: limit,
            offset: this.state.currentOffset,
            context: { mcc_pos_force_filter: true },
        });

        return (result || []).filter((partner) => mccIsPosAvailable(partner));
    },

    clickPartner(partner) {
        if (!mccIsPosAvailable(partner)) {
            this.notification.add(
                _t("Este contacto está oculto o no está disponible para operaciones de POS."),
                { type: "warning" }
            );
            return;
        }
        return super.clickPartner(...arguments);
    },
});
