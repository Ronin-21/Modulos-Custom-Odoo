from odoo import models


class AccountReport(models.Model):
    _inherit = "account.report"

    def get_options(self, previous_options=None):
        """Sanitize malformed cached options coming from the web client.

        In earlier module iterations, the report options payload (especially the
        `journals` list) could be stored in the browser without the keys expected by
        the core initializer `_init_options_journals` (enterprise). That initializer
        runs BEFORE the custom handler and can crash with a KeyError, which the user
        experiences as a redirect back to the database home.

        We only sanitize for our custom expense report.
        """
        po = previous_options
        try:
            is_ours = (
                len(self) == 1
                and self.custom_handler_model_id
                and self.custom_handler_model_id.model in ("prs.expense_account_report.handler", "prs.income_account_report.handler", "prs.cash_balance_statement_report.handler")
            )
        except Exception:
            is_ours = False

        if is_ours and po and isinstance(po, dict):
            journals = po.get("journals")
            bad_journals_cache = False
            if not isinstance(journals, list) or not journals:
                bad_journals_cache = True
            else:
                # Core expects every entry to have "model". If any entry lacks it, we force a rebuild.
                for e in journals:
                    if isinstance(e, dict) and "model" not in e:
                        bad_journals_cache = True
                        break
            if bad_journals_cache:
                po = dict(po)
                po.pop("journals", None)

        options = super().get_options(previous_options=po)

        # After core has built the native journals dropdown, restrict it to liquidity journals.
        # We do it here (NOT in the custom initializer) because at that moment options['journals'] is still empty.
        if is_ours:
            try:
                self.env['prs.expense_account_report.handler']._apply_liquidity_journal_filter(options, po)
            except Exception:
                pass

        return options

    def caret_option_open_record_form(self, options, params):
        """Open the record linked to a report line.

        The enterprise account_reports implementation may receive an `action_param`
        (e.g. 'payment_id') for some custom lines. If the underlying record doesn't
        have that field, the core method crashes with KeyError and the report
        becomes non-interactive.

        We fallback to opening the line's own record by retrying without `action_param`.
        """
        try:
            return super().caret_option_open_record_form(options, params)
        except KeyError as e:
            if str(e) != "'payment_id'":
                raise
            safe_params = dict(params or {})
            safe_params.pop("action_param", None)
            return super().caret_option_open_record_form(options, safe_params)

