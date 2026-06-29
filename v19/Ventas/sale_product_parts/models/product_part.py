# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class ProductPart(models.Model):
    """
    Pieza, repuesto o componente asociado a un producto.
    """
    _name = 'product.part'
    _description = 'Pieza / Repuesto de Producto'
    _order = 'sequence, id'

    product_tmpl_id = fields.Many2one(
        comodel_name='product.template',
        string='Producto',
        required=True,
        ondelete='cascade',
        index=True,
    )
    part_product_id = fields.Many2one(
        comodel_name='product.product',
        string='Pieza / Repuesto',
        required=True,
        domain="[('active', '=', True)]",
    )
    quantity = fields.Float(
        string='Cantidad sugerida',
        default=1.0,
        digits='Product Unit of Measure',
    )
    uom_id = fields.Many2one(
        comodel_name='uom.uom',
        string='Unidad de medida',
        related='part_product_id.uom_id',
        readonly=True,
        store=True,
    )
    sequence = fields.Integer(string='Secuencia', default=10)
    note = fields.Char(string='Nota / Observación')
    auto_load = fields.Boolean(
        string='Pre-seleccionar',
        default=False,
        help='Aparece marcada por defecto en el asistente de inserción.',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Empresa',
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)

    # ─── Stock disponible (seguro sin módulo Inventario) ──────────────────────

    qty_available = fields.Float(
        compute='_compute_qty_available',
        string='Disponible en stock',
        digits='Product Unit of Measure',
    )

    @api.depends('part_product_id')
    def _compute_qty_available(self):
        for part in self:
            product = part.part_product_id
            if product and hasattr(product, 'qty_available'):
                part.qty_available = product.qty_available
            else:
                part.qty_available = 0.0

    # ─── Restricciones ────────────────────────────────────────────────────────

    _sql_constraints = [
        (
            'unique_product_part_per_template',
            'UNIQUE(product_tmpl_id, part_product_id)',
            'Esta pieza ya está asociada a este producto.',
        ),
    ]

    @api.constrains('product_tmpl_id', 'part_product_id')
    def _check_no_self_reference(self):
        for record in self:
            if record.part_product_id.product_tmpl_id == record.product_tmpl_id:
                raise ValidationError(
                    _('Una pieza no puede referenciar al mismo producto padre (%s).')
                    % record.product_tmpl_id.name
                )

    # ─── Acción de inserción en pedido de venta ───────────────────────────────

    def action_insert_in_order(self):
        """
        Inserta los registros product.part seleccionados como líneas reales
        en el pedido de venta.

        Se llama desde el botón de cabecera de la vista lista de selección.
        Requiere en el contexto: sale_order_id y origin_line_id.

        El precio de cada pieza se calcula automáticamente por Odoo
        (_compute_price_unit) al crear la línea con product_id.
        """
        order_id = self.env.context.get('sale_order_id')
        origin_line_id = self.env.context.get('origin_line_id')

        if not order_id or not origin_line_id:
            raise UserError(_(
                'No se encontró el contexto del pedido. '
                'Abra el despiece desde el botón en la línea del pedido de venta.'
            ))

        order = self.env['sale.order'].browse(order_id)
        origin_line = self.env['sale.order.line'].browse(origin_line_id)

        if not order.exists():
            raise UserError(_('El pedido de venta no existe o fue eliminado.'))
        if not origin_line.exists():
            raise UserError(_('La línea de origen no existe o fue eliminada.'))

        child_seqs = origin_line.child_line_ids.mapped('sequence')
        base_seq = max([origin_line.sequence] + child_seqs) if child_seqs else origin_line.sequence

        vals_list = []
        for i, part in enumerate(self, start=1):
            vals_list.append({
                'order_id': order.id,
                'product_id': part.part_product_id.id,
                'product_uom_qty': part.quantity * origin_line.product_uom_qty,
                'product_uom_id': part.uom_id.id,
                'sequence': base_seq + i,
                'is_part_line': True,
                'parent_line_id': origin_line.id,
                'part_source_tmpl_id': origin_line.product_id.product_tmpl_id.id,
            })

        new_lines = self.env['sale.order.line'].create(vals_list)

        # Agregar nota a la descripción auto-computada si existe
        for line, part in zip(new_lines, self):
            if part.note:
                line.name = f'{line.name}\n{part.note}' if line.name else part.note

        origin_line.parts_loaded = True

        return {'type': 'ir.actions.act_window_close'}

    def action_view_part_info(self):
        """
        Abre el wizard informativo personalizado con datos técnicos y de stock.
        Pasa el contexto del pedido de venta para que el botón "Volver"
        pueda re-abrir la lista de despiece correctamente.
        """
        self.ensure_one()

        ctx = self.env.context
        wizard = self.env['product.part.info.wizard'].create_from_part(
            self.id,
            context={
                'sale_order_id': ctx.get('sale_order_id'),
                'origin_line_id': ctx.get('origin_line_id'),
                'parent_product_name': ctx.get('parent_product_name', ''),
            },
        )
        return {
            'type': 'ir.actions.act_window',
            'name': f'Info: {self.part_product_id.display_name}',
            'res_model': 'product.part.info.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
