# -*- coding: utf-8 -*-
from odoo import models


class AccountCardInstallment(models.Model):
    _inherit = 'account.card.installment'

    def _sof_effective_coefficient(self):
        """Coeficiente efectivo para aplicar al cliente.

        Sin 'Trasladar com.': devuelve surcharge_coefficient tal cual.
        Con 'Trasladar com.': multiplica por (1 + comisión_neta), donde
        comisión_neta = fee_percent × (1 + fee_tax_percent) - bank_discount,
        con fallback cascada Plan → Tarjeta → Procesador.
        """
        self.ensure_one()
        coef = self.surcharge_coefficient or 1.0
        if not self.apply_commission_surcharge:
            return coef
        config = self._prs_as_config_dict()
        fee_rate = config.get('fee_percent', 0.0) / 100.0
        fee_tax_rate = config.get('fee_tax_percent', 0.0) / 100.0
        bank_discount_rate = config.get('bank_discount', 0.0) / 100.0
        # Comisión neta: fee + IVA sobre fee - reintegro banco
        net_commission = fee_rate * (1.0 + fee_tax_rate) - bank_discount_rate
        return coef * (1.0 + max(net_commission, 0.0))
