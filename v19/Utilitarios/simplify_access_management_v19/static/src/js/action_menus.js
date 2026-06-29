/** @odoo-module **/

import { ActionMenus } from "@web/search/action_menus/action_menus";
import { patch } from "@web/core/utils/patch";

patch(ActionMenus.prototype, {
    async getActionItems(props) {
        const res = await super.getActionItems(props);
        if (!res.length || !props?.resModel) {
            return res;
        }
        const removedActions = await this.orm.call(
            "access.management",
            "get_remove_options",
            [1, props.resModel]
        );
        return res.filter((item) => !removedActions.includes(item.key));
    },
});
