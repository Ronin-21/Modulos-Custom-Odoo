# -*- coding: utf-8 -*-

from odoo import fields, models


class PosDraftInvoiceErrorWizard(models.TransientModel):
    _name = "pos.draft.invoice.error.wizard"
    _description = "Detalle del error de facturación del POS"

    order_name = fields.Char(string="Orden", readonly=True)
    invoice_name = fields.Char(string="Factura", readonly=True)
    last_attempt_at = fields.Datetime(string="Último intento", readonly=True)
    error_message = fields.Text(string="Detalle del error", readonly=True)
