# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = 'res.company'

    sof_card_surcharge_product_id = fields.Many2one(
        'product.product',
        string='Producto recargo tarjeta',
        domain="[('type', '=', 'service')]",
        help='Producto de servicio para la línea de recargo en factura al cobrar con tarjeta.',
    )


class SaleOpFlowConfigWizard(models.TransientModel):
    _inherit = 'sale.op.flow.config.wizard'

    sof_card_surcharge_product_id = fields.Many2one(
        'product.product',
        string='Producto recargo tarjeta',
        domain="[('type', '=', 'service')]",
        help='Producto de servicio para la línea de recargo en factura al cobrar con tarjeta.',
    )

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        product = self.env.company.sof_card_surcharge_product_id
        res['sof_card_surcharge_product_id'] = product.id if product else False
        return res

    def action_save(self):
        self.env.company.sof_card_surcharge_product_id = self.sof_card_surcharge_product_id
        return super().action_save()
