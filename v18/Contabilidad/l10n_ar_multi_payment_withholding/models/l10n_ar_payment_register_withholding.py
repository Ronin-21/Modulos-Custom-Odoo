# -*- coding: utf-8 -*-
from odoo import api, fields, models


class L10nArPaymentRegisterWithholding(models.TransientModel):
    _inherit = "l10n_ar.payment.register.withholding"

    # Campo editable que el usuario puede modificar para ajustar la retención.
    # Se sincroniza con el cálculo automático via onchange.
    x_manual_amount_value = fields.Monetary(
        string="Cantidad",
        currency_field="currency_id",
    )

    @api.depends(
        "payment_register_id.x_ar_gross_amount",
        "payment_register_id.line_ids",
        "tax_id",
    )
    def _compute_base_amount(self):
        for wth in self:
            gross_amount = abs(wth.payment_register_id.x_ar_gross_amount or 0.0)

            if not gross_amount:
                total_amount = sum(wth.payment_register_id.line_ids.mapped("move_id.amount_total"))
                gross_amount = abs(total_amount)

            if wth.tax_id.l10n_ar_tax_type == "iibb_total":
                wth.base_amount = gross_amount
            else:
                total_invoice_amount = sum(wth.payment_register_id.line_ids.mapped("move_id.amount_total"))
                total_untaxed_amount = sum(wth.payment_register_id.line_ids.mapped("move_id.amount_untaxed"))

                if not total_invoice_amount:
                    wth.base_amount = gross_amount
                else:
                    wth.base_amount = gross_amount * total_untaxed_amount / total_invoice_amount

    def _get_auto_amount(self):
        """Retorna el importe calculado automáticamente por el impuesto."""
        self.ensure_one()
        if not self.tax_id:
            return 0.0
        return self._tax_compute_all_helper()[0]

    @api.depends("base_amount", "tax_id", "x_manual_amount_value")
    def _compute_amount(self):
        for line in self:
            auto = line._get_auto_amount()
            if line.x_manual_amount_value and line.currency_id.compare_amounts(
                line.x_manual_amount_value, auto
            ) != 0:
                line.amount = line.x_manual_amount_value
            else:
                line.amount = auto

    @api.onchange("base_amount", "tax_id")
    def _onchange_sync_manual_value(self):
        """Sincroniza x_manual_amount_value con el cálculo automático."""
        for line in self:
            line.x_manual_amount_value = line._get_auto_amount()

    @api.model_create_multi
    def create(self, vals_list):
        """Inyecta amount en los vals antes del INSERT para satisfacer
        el required=True de la BD, ya que el compute corre después del INSERT."""
        for vals in vals_list:
            if not vals.get("amount"):
                # Construimos un recordset virtual para calcular el monto
                tax_id = vals.get("tax_id")
                base_amount = vals.get("base_amount", 0.0)
                if tax_id and base_amount:
                    tax = self.env["account.tax"].browse(tax_id)
                    if tax.exists():
                        result = tax.compute_all(base_amount)
                        taxes = result.get("taxes", [])
                        vals["amount"] = sum(t.get("amount", 0.0) for t in taxes) if taxes else base_amount
                # Si no se pudo calcular, al menos ponemos 0.0 para no romper el INSERT
                if not vals.get("amount"):
                    vals["amount"] = 0.0
        return super().create(vals_list)