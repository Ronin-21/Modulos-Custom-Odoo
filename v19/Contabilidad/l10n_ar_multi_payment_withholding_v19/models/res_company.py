from odoo import models


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _l10n_ar_get_withholding_base_account(self):
        """Return the configured withholding base account climbing the company tree."""
        self.ensure_one()
        company = self
        while company:
            if company.l10n_ar_tax_base_account_id:
                return company.l10n_ar_tax_base_account_id
            company = company.parent_id
        return self.env['account.account']
