# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class AccountMove(models.Model):
    """Extiende el modelo de Facturas de Contabilidad"""
    _inherit = "account.move"

    picking_ids = fields.One2many(
        'stock.picking',
        'vendor_invoice_id',
        string='Recepciones vinculadas',
        help='Órdenes de recepción relacionadas a esta factura',
    )

    picking_count = fields.Integer(
        string='Cantidad de recepciones',
        compute='_compute_picking_count',
    )

    reception_amount = fields.Monetary(
        string='Monto total de recepciones',
        compute='_compute_reception_amount',
        currency_field='currency_id',
    )

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        """Cantidad de recepciones vinculadas"""
        for move in self:
            move.picking_count = len(move.picking_ids)

    @api.depends('picking_ids.move_ids.product_uom_qty')
    def _compute_reception_amount(self):
        """Monto total de productos recepcionados (a costo estándar)"""
        for move in self:
            total = 0.0
            for picking in move.picking_ids:
                for line in picking.move_ids:
                    if line.product_id:
                        qty = getattr(line, 'product_uom_qty', getattr(line, 'product_qty', 0.0))
                        total += qty * line.product_id.standard_price
            move.reception_amount = total

    @api.constrains('picking_ids', 'move_type')
    def _check_picking_type(self):
        """Solo facturas de proveedor pueden tener recepciones"""
        for move in self:
            if move.picking_ids and move.move_type != 'in_invoice':
                raise ValidationError(
                    _('Solo las facturas de proveedor pueden vincular recepciones.')
                )

    # -------------------------------------------------------------------------
    # NUEVO: generar líneas de factura desde una recepción
    # -------------------------------------------------------------------------
    def _create_lines_from_picking(self, picking):
        """
        Crea líneas de factura (account.move.line) a partir de los movimientos
        de la recepción indicada.
        """
        self.ensure_one()
        if self.move_type != 'in_invoice':
            return

        AccountMoveLine = self.env['account.move.line'].with_context(check_move_validity=False)
        lines_vals = []

        for move in picking.move_ids:
            product = move.product_id
            if not product:
                continue

            qty = getattr(move, 'product_uom_qty', getattr(move, 'product_qty', 0.0))
            if qty <= 0:
                continue

            account = product.property_account_expense_id or product.categ_id.property_account_expense_categ_id
            if not account:
                raise ValidationError(
                    _('El producto %s no tiene una cuenta de gasto configurada.')
                    % product.display_name
                )

            taxes = product.supplier_taxes_id
            if self.partner_id and self.partner_id.property_account_position_id:
                taxes = self.partner_id.property_account_position_id.map_tax(taxes)

            name = move.description_picking or product.display_name

            vals = {
                'move_id': self.id,
                'product_id': product.id,
                'name': name,
                'quantity': qty,
                'price_unit': product.standard_price,
                'account_id': account.id,
                'tax_ids': [(6, 0, taxes.ids)],
                'product_uom_id': (
                    hasattr(move, 'product_uom') and move.product_uom.id
                ) or product.uom_id.id,
                # 👇 importante: marcamos de qué recepción sale la línea
                'picking_id': picking.id,
            }
            lines_vals.append(vals)

        if lines_vals:
            AccountMoveLine.create(lines_vals)

    def action_clear_receptions(self):
        """
        Quita las recepciones vinculadas a la factura y elimina
        las líneas de factura generadas desde esos remitos.
        """
        self.ensure_one()

        if self.state != 'draft':
            raise UserError(_('Solo puede quitar recepciones en facturas en borrador.'))

        if not self.picking_ids:
            raise UserError(_('No hay recepciones vinculadas a esta factura.'))

        # Guardamos los remitos vinculados antes de soltar la relación
        pickings = self.picking_ids

        # 1) Quitar vínculo en los remitos
        pickings.write({'vendor_invoice_id': False})

        # 2) Borrar líneas de factura asociadas a esos remitos
        lines_to_delete = self.line_ids.filtered(lambda l: l.picking_id in pickings)
        lines_to_delete.unlink()

        # El compute de picking_ids/picking_count se recalcula solo
        return True

    # -------------------------------------------------------------------------
    # Acciones de botones
    # -------------------------------------------------------------------------
    def action_view_receptions(self):
        """Abre la lista de recepciones vinculadas"""
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

        # Validamos que haya al menos una recepción candidata
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
        """
        Smart button:
        - Si ya hay recepciones -> abre la lista.
        - Si no hay -> abre el wizard para elegir una recepción existente.
        """
        self.ensure_one()
        if self.picking_ids:
            return self.action_view_receptions()
        return self.action_link_reception()
