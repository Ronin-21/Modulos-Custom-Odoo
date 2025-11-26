# models/stock_picking.py
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class StockPickingReceipt(models.Model):
    _inherit = "stock.picking"

    vendor_invoice_id = fields.Many2one(
        'account.move',
        string='Factura de proveedor',
        domain="[('move_type', '=', 'in_invoice'), ('partner_id', '=', partner_id)]",
        help='Factura de proveedor relacionada a esta recepción',
    )
    invoice_reference = fields.Char(
        related='vendor_invoice_id.name',
        string='Número de factura',
        readonly=True,
    )

    @api.constrains('vendor_invoice_id', 'partner_id')
    def _check_invoice_partner(self):
        for picking in self:
            if picking.vendor_invoice_id and picking.partner_id \
               and picking.vendor_invoice_id.partner_id != picking.partner_id:
                raise ValidationError(
                    _('La factura debe pertenecer al mismo proveedor de la recepción.')
                )

    def action_open_vendor_invoice(self):
        """Smart button: abre la factura vinculada."""
        self.ensure_one()
        if not self.vendor_invoice_id:
            raise UserError(_('No hay factura de proveedor vinculada a esta recepción.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Factura de proveedor'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.vendor_invoice_id.id,
            'target': 'current',
        }
