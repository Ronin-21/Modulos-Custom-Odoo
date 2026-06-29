# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class SaleInstallationMaterialLine(models.Model):
    _name = 'sale.installation.material.line'
    _description = 'Línea de Control de Materiales de Instalación'
    _order = 'installation_id, id'

    installation_id = fields.Many2one(
        'sale.installation.material', string='Control', required=True,
        ondelete='cascade', index=True)
    sale_order_line_id = fields.Many2one(
        'sale.order.line', string='Línea de Venta', readonly=True, ondelete='set null')
    company_id = fields.Many2one(related='installation_id.company_id', store=True)
    state = fields.Selection(related='installation_id.state', store=True, string='Estado')

    product_id = fields.Many2one('product.product', string='Producto', required=True, readonly=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unidad', readonly=True)
    currency_id = fields.Many2one(related='installation_id.currency_id', readonly=True)
    price_unit = fields.Float(string='Precio unitario', readonly=True, digits='Product Price')

    original_qty = fields.Float(
        string='Presupuestado', readonly=True, digits='Product Unit of Measure',
        help='Cantidad originalmente presupuestada en la venta. No cambia con los movimientos.')

    move_ids = fields.One2many('stock.move', 'installation_line_id', string='Movimientos')

    reserved_qty = fields.Float(
        string='Reservado', compute='_compute_move_qties', store=True,
        digits='Product Unit of Measure')
    withdrawn_qty = fields.Float(
        string='Retirado', compute='_compute_move_qties', store=True,
        digits='Product Unit of Measure')
    returned_qty = fields.Float(
        string='Devuelto', compute='_compute_move_qties', store=True,
        digits='Product Unit of Measure')
    released_qty = fields.Float(
        string='Liberado', compute='_compute_move_qties', store=True,
        digits='Product Unit of Measure')

    used_qty = fields.Float(
        string='Usado real', compute='_compute_derived_qties', store=True,
        digits='Product Unit of Measure',
        help='Consumo real = retirado - devuelto.')
    in_installer_qty = fields.Float(
        string='En poder del instalador', compute='_compute_derived_qties', store=True,
        digits='Product Unit of Measure',
        help='Material retirado y todavía no devuelto = retirado - devuelto.')
    pending_qty = fields.Float(
        string='Pendiente', compute='_compute_derived_qties', store=True,
        digits='Product Unit of Measure',
        help='Disponible para retirar = presupuestado - usado real.')
    qty_to_invoice = fields.Float(
        string='A facturar', compute='_compute_derived_qties', store=True,
        digits='Product Unit of Measure')

    # ------------------------------------------------------------------
    @api.depends('move_ids.state', 'move_ids.quantity', 'move_ids.installation_move_type')
    def _compute_move_qties(self):
        for line in self:
            done = line.move_ids.filtered(lambda m: m.state == 'done')
            uom = line.product_uom_id

            def _sum(move_type):
                total = 0.0
                for m in done.filtered(lambda mv: mv.installation_move_type == move_type):
                    total += m.product_uom._compute_quantity(
                        m.quantity, uom, rounding_method='HALF-UP') if uom else m.quantity
                return total

            line.reserved_qty = _sum('reserve')
            line.withdrawn_qty = _sum('withdraw')
            line.returned_qty = _sum('return')
            line.released_qty = _sum('release')

    @api.depends('original_qty', 'withdrawn_qty', 'returned_qty')
    def _compute_derived_qties(self):
        for line in self:
            used = line.withdrawn_qty - line.returned_qty
            line.used_qty = used
            line.in_installer_qty = used
            line.pending_qty = line.original_qty - used
            line.qty_to_invoice = used

    # ------------------------------------------------------------------
    @api.constrains('withdrawn_qty', 'returned_qty', 'original_qty')
    def _check_quantities(self):
        for line in self:
            rounding = line.product_uom_id.rounding or 0.01
            if float_compare(line.returned_qty, line.withdrawn_qty, precision_rounding=rounding) > 0:
                raise ValidationError(_(
                    'La cantidad devuelta (%(ret)s) no puede superar la retirada (%(wd)s) '
                    'para %(prod)s.',
                    ret=line.returned_qty, wd=line.withdrawn_qty,
                    prod=line.product_id.display_name))
            if float_compare(line.used_qty, line.original_qty, precision_rounding=rounding) > 0:
                raise ValidationError(_(
                    'El consumo real (%(used)s) no puede superar lo presupuestado (%(orig)s) '
                    'para %(prod)s.',
                    used=line.used_qty, orig=line.original_qty,
                    prod=line.product_id.display_name))
