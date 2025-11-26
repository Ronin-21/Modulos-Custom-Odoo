# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PickingReceptionWizard(models.TransientModel):
    """Asistente para vincular recepciones a facturas"""
    _name = 'reception.invoice.wizard'
    _description = 'Vinculación de Recepción a Factura'

    invoice_id = fields.Many2one(
        'account.move',
        string='Factura',
        required=True,
        ondelete='cascade',
    )

    # Proveedor de la factura, para usarlo en el dominio
    partner_id = fields.Many2one(
        'res.partner',
        string='Proveedor',
        related='invoice_id.partner_id',
        readonly=True,
    )

    picking_id = fields.Many2one(
        'stock.picking',
        string='Recepción',
        required=True,
        ondelete='cascade',
        # el filtro real lo ponemos en la vista XML con domain="[...]"
    )

    @api.onchange('picking_id')
    def _onchange_picking(self):
        """Segunda defensa: la recepción debe ser del mismo proveedor."""
        if self.picking_id and self.partner_id:
            if self.picking_id.partner_id != self.partner_id:
                raise ValidationError(
                    _('La recepción debe ser del mismo proveedor de la factura.')
                )

    def action_link(self):
        """Vincula la recepción a la factura."""
        self.ensure_one()
        self.picking_id.vendor_invoice_id = self.invoice_id.id
        return {'type': 'ir.actions.act_window_close'}
