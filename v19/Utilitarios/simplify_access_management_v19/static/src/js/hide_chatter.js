/** @odoo-module **/

import { Chatter } from "@mail/chatter/web_portal/chatter";
import { session } from "@web/session";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { onMounted, useState } from "@odoo/owl";
import { user } from "@web/core/user";

patch(Chatter.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.access = useState({
            hide_log_notes: false,
            hide_send_mail: false,
            hide_schedule_activity: false,
        });
        onMounted(async () => {
            const model = this.props.threadModel;
            const companyId =
                user.activeCompany?.id ||
                user.context?.allowed_company_ids?.[0] ||
                session.user_companies?.current_company ||
                session.user_context?.allowed_company_ids?.[0] ||
                false;
            const userId = user.userId || session.uid || false;
            if (!model || !userId) {
                return;
            }
            try {
                const result = await this.orm.call(
                    "access.management",
                    "get_chatter_hide_details",
                    [userId, companyId, model]
                );
                Object.assign(this.access, result || {});
            } catch (_error) {
                // Do not crash the chatter if the access lookup fails.
            }
        });
    },
});
