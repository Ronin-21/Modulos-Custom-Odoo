# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProductPartInfoWizard(models.TransientModel):
    """
    Wizard informativo de una pieza/repuesto. 100% solo lectura.
    Sin modelos intermedios: las ubicaciones se renderizan como HTML
    para evitar popups redundantes al hacer clic en filas.
    """
    _name = 'product.part.info.wizard'
    _description = 'Información de Pieza / Repuesto'

    # ─── Contexto para volver al despiece ─────────────────────────────────────

    part_id = fields.Many2one('product.part', readonly=True)
    product_tmpl_id = fields.Many2one('product.template', readonly=True)
    sale_order_id = fields.Many2one('sale.order', readonly=True)
    origin_line_id = fields.Many2one('sale.order.line', readonly=True)
    parent_product_name = fields.Char(readonly=True)

    # ─── Identificación ───────────────────────────────────────────────────────

    product_id = fields.Many2one('product.product', readonly=True)
    product_ref = fields.Char(string='Referencia interna', readonly=True)
    barcode = fields.Char(string='Código de barras', readonly=True)
    categ_id = fields.Many2one('product.category', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='Unidad de medida', readonly=True)
    product_type = fields.Char(string='Tipo', readonly=True)

    # ─── Despiece ─────────────────────────────────────────────────────────────

    quantity_suggested = fields.Float(
        string='Cantidad sugerida en despiece',
        readonly=True,
        digits='Product Unit of Measure',
    )
    note = fields.Char(string='Nota del despiece', readonly=True)

    # ─── Precios ──────────────────────────────────────────────────────────────

    list_price = fields.Float(string='Precio de venta', readonly=True, digits='Product Price')
    standard_price = fields.Float(string='Costo', readonly=True, digits='Product Price')

    # ─── Stock totales ────────────────────────────────────────────────────────

    qty_available = fields.Float(string='Disponible', readonly=True, digits='Product Unit of Measure')
    virtual_available = fields.Float(string='Cantidad prevista', readonly=True, digits='Product Unit of Measure')
    qty_in = fields.Float(string='Entradas pendientes', readonly=True, digits='Product Unit of Measure')
    qty_out = fields.Float(string='Salidas pendientes', readonly=True, digits='Product Unit of Measure')

    # ─── Ubicaciones como HTML (sin modelo intermedio, sin popups) ────────────

    location_html = fields.Html(
        string='Stock por ubicación',
        readonly=True,
        sanitize=False,
    )
    has_stock_module = fields.Boolean(readonly=True, default=False)

    # ─── Creación ─────────────────────────────────────────────────────────────

    @api.model
    def create_from_part(self, part_id, context=None):
        context = context or {}
        part = self.env['product.part'].browse(part_id)
        product = part.part_product_id

        type_labels = {'consu': 'Consumible', 'service': 'Servicio', 'combo': 'Combo'}
        product_type = ''
        if hasattr(product, 'detailed_type'):
            product_type = type_labels.get(product.detailed_type, product.detailed_type)

        has_stock = 'stock.quant' in self.env.registry

        vals = {
            'part_id': part.id,
            'product_tmpl_id': part.product_tmpl_id.id,
            'sale_order_id': context.get('sale_order_id'),
            'origin_line_id': context.get('origin_line_id'),
            'parent_product_name': context.get('parent_product_name', ''),
            'product_id': product.id,
            'product_ref': product.default_code or '',
            'barcode': product.barcode or '',
            'categ_id': product.categ_id.id if product.categ_id else False,
            'uom_id': product.uom_id.id if product.uom_id else False,
            'product_type': product_type,
            'list_price': product.list_price or 0.0,
            'standard_price': product.standard_price or 0.0,
            'quantity_suggested': part.quantity,
            'note': part.note or '',
            'has_stock_module': has_stock,
        }

        if has_stock:
            vals['qty_available'] = product.qty_available or 0.0
            vals['virtual_available'] = product.virtual_available or 0.0
            vals['qty_in'] = product.incoming_qty or 0.0
            vals['qty_out'] = product.outgoing_qty or 0.0
            vals['location_html'] = self._build_location_html(product)

        return self.create(vals)

    def _build_location_html(self, product):
        """
        Construye una tabla HTML de ubicaciones con stock.
        Al ser un campo Html, no hay filas clickeables ni popups posibles.
        """
        if 'stock.quant' not in self.env.registry:
            return ''

        quants = self.env['stock.quant'].search([
            ('product_id', '=', product.id),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
        ], order='quantity desc')

        if not quants:
            return (
                '<p class="text-muted mb-0">'
                '<i class="fa fa-info-circle"/> Sin stock en ubicaciones internas.'
                '</p>'
            )

        uom = product.uom_id.name or ''
        rows = ''
        for q in quants:
            loc = q.location_id.complete_name or q.location_id.name
            disponible = q.quantity - (q.reserved_quantity or 0.0)
            rows += (
                f'<tr>'
                f'<td style="padding:4px 8px;">{loc}</td>'
                f'<td style="padding:4px 8px; text-align:right;">{q.quantity:.2f}</td>'
                f'<td style="padding:4px 8px; text-align:right;">{q.reserved_quantity or 0.0:.2f}</td>'
                f'<td style="padding:4px 8px; text-align:right; font-weight:600;">{disponible:.2f}</td>'
                f'<td style="padding:4px 8px; color:#888;">{uom}</td>'
                f'</tr>'
            )

        return (
            '<table style="width:100%; border-collapse:collapse; font-size:13px;">'
            '<thead>'
            '<tr style="background:#f5f5f5; border-bottom:1px solid #ddd;">'
            '<th style="padding:6px 8px; text-align:left; font-weight:600;">Ubicación</th>'
            '<th style="padding:6px 8px; text-align:right; font-weight:600;">Cant. física</th>'
            '<th style="padding:6px 8px; text-align:right; font-weight:600;">Reservado</th>'
            '<th style="padding:6px 8px; text-align:right; font-weight:600;">Disponible</th>'
            '<th style="padding:6px 8px; font-weight:600;">Unidad</th>'
            '</tr>'
            '</thead>'
            f'<tbody>{rows}</tbody>'
            '</table>'
        )

    # ─── Volver al despiece ───────────────────────────────────────────────────

    def action_go_back(self):
        self.ensure_one()
        list_view_id = self.env.ref('sale_product_parts.product_part_list_view_selection').id
        search_view_id = self.env.ref('sale_product_parts.product_part_search_view_selection').id
        title = f'Despiece: {self.parent_product_name}' if self.parent_product_name else 'Despiece'
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': 'product.part',
            'view_mode': 'list',
            'domain': [('product_tmpl_id', '=', self.product_tmpl_id.id)],
            'views': [(list_view_id, 'list')],
            'search_view_id': [search_view_id, 'search'],
            'context': {
                'sale_order_id': self.sale_order_id.id,
                'origin_line_id': self.origin_line_id.id,
                'parent_product_name': self.parent_product_name,
            },
            'target': 'new',
        }
