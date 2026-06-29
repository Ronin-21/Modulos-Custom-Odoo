# -*- coding: utf-8 -*-
"""Compat shim for Odoo 18 bank reconciliation widget.

Some earlier iterations introduced a `bank_rec_widget.py` inheriting from
`models.TransientModel`, which breaks the registry in Odoo 18 because
`bank.rec.widget` is a regular `models.Model`.

This file intentionally does *not* override any behavior; it only guarantees
the inheritance base class is correct, preventing registry crashes.
"""

from odoo import models


class BankRecWidget(models.Model):
    _inherit = "bank.rec.widget"
