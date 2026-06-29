/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { BankRecButtonList } from "@account_accountant/components/bank_reconciliation/button_list/button_list";
import { BankReconciliationService } from "@account_accountant/components/bank_reconciliation/bank_reconciliation_service";

/**
 * Restringe el dominio del diálogo "Buscar: Apuntes contables por conciliar"
 * y del contador "Conciliar X" para que los apuntes de pago pendientes
 * (payment_id != False) solo aparezcan si pertenecen al mismo diario que
 * la línea de extracto. Los asientos manuales (payment_id = False) siguen
 * siendo visibles sin restricción.
 */
patch(BankRecButtonList.prototype, {
    getReconcileButtonDomain() {
        const domain = super.getReconcileButtonDomain();
        const journalId = this.statementLineData?.journal_id?.id;
        if (!journalId) {
            return domain;
        }
        return [...domain, "|", ["journal_id", "=", journalId], ["payment_id", "=", false]];
    },
});

patch(BankReconciliationService.prototype, {
    getAvailableReconciledLinesDomain(records) {
        const domain = super.getAvailableReconciledLinesDomain(records);
        const journalIds = [
            ...new Set(records.map((r) => r.data?.journal_id?.id).filter(Boolean)),
        ];
        if (!journalIds.length) {
            return domain;
        }
        return [...domain, "|", ["journal_id", "in", journalIds], ["payment_id", "=", false]];
    },
});
