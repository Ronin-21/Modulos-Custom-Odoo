# -*- coding: utf-8 -*-
from odoo import models
from urllib.parse import quote_plus


class AccountMove(models.Model):
    _inherit = "account.move"

    def _thermal_afip_qr_src(self, width=240, height=240):
        """QR AFIP: URL absoluta (wkhtmltopdf) + urlencode."""
        self.ensure_one()
        qr = getattr(self, "l10n_ar_afip_qr_code", False)
        if not qr:
            return False

        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        base_url = base_url.rstrip("/")
        val = quote_plus(qr)

        # /report/barcode soporta type/value (y a veces legacy barcode_type/val)
        return (
            f"{base_url}/report/barcode/?"
            f"type=QR&value={val}"
            f"&barcode_type=QR&val={val}"
            f"&width={int(width)}&height={int(height)}"
        )
