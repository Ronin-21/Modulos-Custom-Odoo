from odoo import api, fields, models

PARAM_REQUIRE_INVOICE = 'sale_invoice_delivery_control.require_posted_invoice_before_delivery'
PARAM_WARN_REFUND = 'sale_invoice_delivery_control.warn_refund_on_delivered_goods'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    require_posted_invoice_before_delivery = fields.Boolean(
        string='Exigir factura confirmada antes de entregar mercadería',
        help=(
            'Si está activo, el sistema bloqueará la validación de entregas de salida '
            'de productos almacenables cuando la orden de venta no tenga al menos una '
            'factura de cliente confirmada (publicada).'
        ),
        config_parameter=PARAM_REQUIRE_INVOICE,
    )

    warn_refund_on_delivered_goods = fields.Boolean(
        string='Controlar notas de crédito sobre mercadería entregada',
        help=(
            'Si está activo:\n'
            '- Sin devolución: bloquea la creación de la NC (modal informativo).\n'
            '- Devolución parcial: crea la NC ajustando automáticamente las cantidades '
            'a lo efectivamente devuelto (descontando NCs anteriores ya emitidas).\n'
            '- Devolución total: flujo normal sin intervención.'
        ),
        config_parameter=PARAM_WARN_REFUND,
    )

    def set_values(self):
        """Persiste los valores como ir.config_parameter (True/False como string)."""
        super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param(PARAM_REQUIRE_INVOICE, str(self.require_posted_invoice_before_delivery))
        ICP.set_param(PARAM_WARN_REFUND, str(self.warn_refund_on_delivered_goods))

    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()
        res['require_posted_invoice_before_delivery'] = (
            ICP.get_param(PARAM_REQUIRE_INVOICE, default='True') == 'True'
        )
        res['warn_refund_on_delivered_goods'] = (
            ICP.get_param(PARAM_WARN_REFUND, default='True') == 'True'
        )
        return res
