# models/account_move.py
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    picking_ids = fields.One2many(
        'stock.picking',
        'vendor_invoice_id',
        string='Recepciones vinculadas',
    )
    picking_count = fields.Integer(compute='_compute_picking_count')
    reception_amount = fields.Monetary(
        compute='_compute_reception_amount',
        currency_field='currency_id',
    )

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for move in self:
            move.picking_count = len(move.picking_ids)

    @api.depends('picking_ids.move_ids.product_uom_qty')
    def _compute_reception_amount(self):
        for move in self:
            total = 0.0
            for picking in move.picking_ids:
                for line in picking.move_ids:
                    if line.product_id:
                        qty = getattr(line, 'product_uom_qty', line.product_qty)
                        total += qty * line.product_id.standard_price
            move.reception_amount = total

    @api.constrains('picking_ids', 'move_type')
    def _check_picking_type(self):
        for move in self:
            if move.picking_ids and move.move_type != 'in_invoice':
                raise ValidationError(
                    _('Solo las facturas de proveedor pueden vincular recepciones.')
                )

    def action_view_receptions(self):
        self.ensure_one()
        if not self.picking_ids:
            raise UserError(_('No hay recepciones vinculadas a esta factura.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Recepciones vinculadas'),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.picking_ids.ids)],
            'context': {'create': False},
        }

    def action_link_reception(self):
        """Abre el wizard para elegir una recepción YA HECHA."""
        self.ensure_one()
        if self.move_type != 'in_invoice':
            raise UserError(_('Solo las facturas de proveedor pueden vincular recepciones.'))

        domain = [
            ('partner_id', '=', self.partner_id.id),
            ('picking_type_code', '=', 'incoming'),
            ('state', '=', 'done'),
            ('vendor_invoice_id', '=', False),
        ]
        has_picking = bool(self.env['stock.picking'].search(domain, limit=1))
        if not has_picking:
            raise UserError(
                _('No hay recepciones disponibles del proveedor %s sin factura vinculada.')
                % (self.partner_id.display_name or self.partner_id.name)
            )

        action = self.env.ref('reception_invoice_link.action_reception_invoice_wizard').read()[0]
        action['context'] = {
            'default_invoice_id': self.id,
        }
        return action

    def action_open_receptions(self):
        """Botón inteligente de la factura."""
        self.ensure_one()
        if self.picking_ids:
            return self.action_view_receptions()
        return self.action_link_reception()
