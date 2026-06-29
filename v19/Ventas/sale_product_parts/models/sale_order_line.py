# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaleOrderLine(models.Model):
    """
    Extensión de sale.order.line para Odoo 19 — soporte de jerarquía padre/pieza.
    """
    _inherit = 'sale.order.line'

    is_part_line = fields.Boolean(
        string='Es línea de pieza',
        default=False,
        copy=False,
    )
    parent_line_id = fields.Many2one(
        comodel_name='sale.order.line',
        string='Línea principal',
        ondelete='set null',
        copy=False,
        index=True,
    )
    child_line_ids = fields.One2many(
        comodel_name='sale.order.line',
        inverse_name='parent_line_id',
        string='Líneas de piezas',
        copy=False,
    )
    part_source_tmpl_id = fields.Many2one(
        comodel_name='product.template',
        string='Producto origen del despiece',
        copy=False,
        readonly=True,
    )
    has_product_parts = fields.Boolean(
        compute='_compute_has_product_parts',
        string='Tiene despiece',
        store=True,
    )
    part_count = fields.Integer(
        compute='_compute_has_product_parts',
        string='N° de piezas',
        store=True,
    )
    parts_loaded = fields.Boolean(
        string='Piezas insertadas',
        default=False,
        copy=False,
    )

    @api.depends('product_id', 'product_id.product_tmpl_id.part_ids')
    def _compute_has_product_parts(self):
        for line in self:
            if line.product_id and line.product_id.product_tmpl_id:
                parts = line.product_id.product_tmpl_id.part_ids
                line.part_count = len(parts)
                line.has_product_parts = bool(parts)
            else:
                line.part_count = 0
                line.has_product_parts = False

    def unlink(self):
        part_lines_being_deleted = self.filtered('is_part_line')
        parents_to_check = part_lines_being_deleted.mapped('parent_line_id').filtered(
            lambda l: l.exists()
        )
        result = super().unlink()
        for parent in parents_to_check:
            if parent.exists() and not parent.child_line_ids:
                parent.parts_loaded = False
        return result

    def action_open_parts_wizard(self):
        """
        Abre la lista nativa de product.part con buscador, filtros y grupos.

        Se abre como target='new' (dialog) con:
        - Buscador nativo de Odoo (field + filtros + grupos)
        - Selección múltiple estándar de Odoo (checkboxes de fila)
        - Botón de cabecera "Insertar en pedido" para los seleccionados

        El contexto pasa sale_order_id y origin_line_id para que
        action_insert_in_order en product.part sepa dónde insertar.
        """
        self.ensure_one()

        if not self.has_product_parts:
            raise UserError(_(
                'El producto "%s" no tiene piezas definidas en su despiece.'
            ) % self.product_id.display_name)

        tmpl = self.product_id.product_tmpl_id

        list_view_id = self.env.ref(
            'sale_product_parts.product_part_list_view_selection'
        ).id
        search_view_id = self.env.ref(
            'sale_product_parts.product_part_search_view_selection'
        ).id

        return {
            'type': 'ir.actions.act_window',
            'name': _('Despiece: %s') % self.product_id.display_name,
            'res_model': 'product.part',
            'view_mode': 'list',
            'domain': [('product_tmpl_id', '=', tmpl.id)],
            'views': [(list_view_id, 'list')],
            'search_view_id': [search_view_id, 'search'],
            'context': {
                'sale_order_id': self.order_id.id,
                'origin_line_id': self.id,
                'parent_product_name': self.product_id.display_name,
            },
            'target': 'new',
        }

    def action_update_part_quantities(self):
        """
        Actualiza las cantidades de las líneas de piezas hijas.
        Recalcula: qty_pieza = qty_sugerida_en_despiece × qty_padre_actual.
        No modifica precios, solo cantidades.
        """
        self.ensure_one()

        if not self.child_line_ids:
            raise UserError(_('Esta línea no tiene piezas insertadas para actualizar.'))

        tmpl = self.product_id.product_tmpl_id
        updated = 0

        for child in self.child_line_ids:
            if not child.part_source_tmpl_id:
                continue
            part = self.env['product.part'].search([
                ('product_tmpl_id', '=', tmpl.id),
                ('part_product_id', '=', child.product_id.id),
            ], limit=1)
            if part:
                child.product_uom_qty = part.quantity * self.product_uom_qty
                updated += 1

        if not updated:
            raise UserError(_('No se encontraron piezas coincidentes para actualizar.'))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cantidades actualizadas'),
                'message': _('%d línea(s) de piezas actualizadas.') % updated,
                'type': 'success',
                'sticky': False,
            },
        }
