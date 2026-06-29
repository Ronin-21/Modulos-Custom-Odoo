/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import { onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

patch(CogMenu.prototype, {
    setup() {
        super.setup();
        this.access = useState({ removeSpreadsheet: false, exportHideButton: false });
        const loadAccess = async () => {
            if (this?.env?.config?.actionType !== "ir.actions.act_window") {
                this.access.removeSpreadsheet = false;
                this.access.exportHideButton = false;
                return;
            }
            this.access.removeSpreadsheet = await this.orm.call(
                "access.management",
                "is_spread_sheet_available",
                [1, this?.env?.config?.actionType, this?.env?.config?.actionId]
            );
            const removed = await this.orm.call(
                "access.management",
                "get_remove_options",
                [1, this.props.resModel]
            );
            this.access.exportHideButton = removed.includes("export");
        };
        onWillStart(loadAccess);
        onWillUpdateProps(loadAccess);
    },

    get cogItems() {
        let res = super.cogItems;
        if (this.access.removeSpreadsheet) {
            res = res.filter((item) => item.key !== "SpreadsheetCogMenu");
        }
        if (this.access.exportHideButton) {
            res = res.filter((item) => item.key !== "ExportAll");
        }
        return res;
    },
});
