# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaleProductPartWizard(models.TransientModel):
    """
    Asistente para visualizar e insertar piezas/repuestos en un pedido de venta.
    """
    _name = 'sale.product.part.wizard'
    _description = 'Asistente de inserción de piezas en pedido de venta'

    order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Pedido de venta',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    origin_line_id = fields.Many2one(
        comodel_name='sale.order.line',
        string='Línea de origen',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        related='origin_line_id.product_id',
        string='Producto de referencia',
        readonly=True,
    )
    origin_qty = fields.Float(
        related='origin_line_id.product_uom_qty',
        string='Cantidad en pedido',
        readonly=True,
        digits='Product Unit of Measure',
    )
    origin_uom_id = fields.Many2one(
        comodel_name='uom.uom',
        related='origin_line_id.product_uom_id',
        string='Unidad',
        readonly=True,
    )
    search_term = fields.Char(
        string='Buscar pieza',
        default='',
        help='Filtre las piezas por nombre de producto.',
    )
    wizard_line_ids = fields.One2many(
        comodel_name='sale.product.part.wizard.line',
        inverse_name='wizard_id',
        string='Piezas disponibles',
    )

    def action_insert_parts(self):
        """Inserta las piezas seleccionadas como líneas reales en el pedido."""
        self.ensure_one()

        selected = self.wizard_line_ids.filtered(
            lambda l: l.selected and not l.already_loaded
        )
        if not selected:
            raise UserError(_(
                'No hay piezas nuevas seleccionadas para insertar.\n\n'
                'Las piezas marcadas como "Ya insertada" ya están en el pedido. '
                'Use el botón "Actualizar cantidades" para sincronizar sus cantidades.'
            ))

        origin = self.origin_line_id
        order = self.order_id

        child_seqs = origin.child_line_ids.mapped('sequence')
        base_seq = max([origin.sequence] + child_seqs) if child_seqs else origin.sequence

        vals_list = []
        for i, wline in enumerate(selected, start=1):
            vals_list.append({
                'order_id': order.id,
                'product_id': wline.product_id.id,
                'product_uom_qty': wline.quantity,
                'product_uom_id': wline.uom_id.id,
                'sequence': base_seq + i,
                'is_part_line': True,
                'parent_line_id': origin.id,
                'part_source_tmpl_id': origin.product_id.product_tmpl_id.id,
            })

        new_lines = self.env['sale.order.line'].create(vals_list)

        for line, wline in zip(new_lines, selected):
            if wline.note:
                line.name = f'{line.name}\n{wline.note}' if line.name else wline.note

        origin.parts_loaded = True

        return {'type': 'ir.actions.act_window_close'}

    def action_update_quantities(self):
        """Actualiza las cantidades de las piezas ya insertadas."""
        self.ensure_one()

        already_loaded = self.wizard_line_ids.filtered('already_loaded')
        if not already_loaded:
            raise UserError(_(
                'No hay piezas previamente insertadas para actualizar. '
                'Use "Insertar seleccionadas" para agregar piezas al pedido.'
            ))

        origin = self.origin_line_id
        tmpl = origin.product_id.product_tmpl_id
        updated = 0

        for wline in already_loaded:
            part = self.env['product.part'].search([
                ('product_tmpl_id', '=', tmpl.id),
                ('part_product_id', '=', wline.product_id.id),
            ], limit=1)

            if not part:
                continue

            matching_children = origin.child_line_ids.filtered(
                lambda l: l.product_id == wline.product_id
            )
            new_qty = part.quantity * origin.product_uom_qty
            for child in matching_children:
                child.product_uom_qty = new_qty
                updated += 1

        return {'type': 'ir.actions.act_window_close'}


class SaleProductPartWizardLine(models.TransientModel):
    """
    Línea del asistente de inserción de piezas.
    """
    _name = 'sale.product.part.wizard.line'
    _description = 'Línea del asistente de piezas'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        comodel_name='sale.product.part.wizard',
        string='Asistente',
        required=True,
        ondelete='cascade',
    )
    part_id = fields.Many2one(
        comodel_name='product.part',
        string='Pieza de referencia',
        readonly=True,
    )
    sequence = fields.Integer(string='Sec.', default=10)

    # ─── Info de la pieza ─────────────────────────────────────────────────────

    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Pieza / Repuesto',
        readonly=True,
    )
    uom_id = fields.Many2one(
        comodel_name='uom.uom',
        string='Unidad de medida',
        readonly=True,
    )
    note = fields.Char(string='Nota', readonly=True)

    # ─── Campos editables ─────────────────────────────────────────────────────

    quantity = fields.Float(
        string='Cantidad',
        digits='Product Unit of Measure',
        help='Cantidad a insertar. Precalculada como: qty_sugerida × qty_padre.',
    )
    selected = fields.Boolean(
        string='Insertar',
        default=False,
    )

    # ─── Estado ───────────────────────────────────────────────────────────────

    already_loaded = fields.Boolean(
        string='Ya insertada',
        readonly=True,
        default=False,
    )

    # ─── Info extra para popup readonly ──────────────────────────────────────

    product_ref = fields.Char(
        related='product_id.default_code',
        string='Referencia interna',
        readonly=True,
    )
    qty_available = fields.Float(
        compute='_compute_qty_available',
        string='Disponible en stock',
        digits='Product Unit of Measure',
    )

    @api.depends('product_id')
    def _compute_qty_available(self):
        """
        Stock disponible del producto.
        Seguro si el módulo de Inventario no está instalado: retorna 0.
        """
        for line in self:
            product = line.product_id
            if product and hasattr(product, 'qty_available'):
                line.qty_available = product.qty_available
            else:
                line.qty_available = 0.0
