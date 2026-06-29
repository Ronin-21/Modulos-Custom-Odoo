# -*- coding: utf-8 -*-
"""Silence a noisy precompute warning in Odoo 17/18 logs.

This warning is harmless but can flood logs in Odoo SH:
Field account.payment.partner_id cannot be precomputed as it depends on non-precomputed field account.payment.is_internal_transfer
"""

import warnings

warnings.filterwarnings(
    "ignore",
    message=r"Field account\.payment\.partner_id cannot be precomputed.*",
    category=UserWarning,
)
