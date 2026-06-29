# -*- coding: utf-8 -*-
import html

from odoo import models, fields, api


class SofProductBranchStockWizard(models.TransientModel):
    _name = 'sof.product.branch.stock.wizard'
    _description = 'Consultar stock del producto en todas las sucursales'

    product_id = fields.Many2one('product.product', string='Producto', required=True)
    # True cuando se abre desde la línea de un pedido (producto fijo, solo lectura).
    # False desde el menú "Consultar Stock" (editable para buscar cualquier producto).
    lock_product = fields.Boolean(default=False)
    uom_name = fields.Char(string='Unidad', compute='_compute_stock')
    total_available = fields.Float(
        string='Disponible total (todas las sucursales)', compute='_compute_stock',
        digits='Product Unit of Measure',
    )
    stock_html = fields.Html(
        string='Stock por sucursal', compute='_compute_stock', sanitize=False,
    )

    @api.depends('product_id')
    def _compute_stock(self):
        for wiz in self:
            product = wiz.product_id
            wiz.uom_name = product.uom_id.name or ''
            if not product:
                wiz.total_available = 0.0
                wiz.stock_html = ''
                continue
            rows, total = wiz._collect_branch_stock(product)
            wiz.total_available = total
            wiz.stock_html = wiz._render_html(rows, product)

    def _collect_branch_stock(self, product):
        """Disponibilidad por almacén/sucursal. Lee TODAS las compañías con sudo() para que
        el cajero/vendedor vea el stock de las demás sucursales (no solo la suya)."""
        Quant = self.env['stock.quant'].sudo()
        quants = Quant.search([
            ('product_id', '=', product.id),
            ('location_id.usage', '=', 'internal'),
        ])
        per_wh = {}
        for q in quants:
            wh = q.location_id.warehouse_id
            if not wh:
                continue
            data = per_wh.setdefault(wh.id, {'qty': 0.0, 'reserved': 0.0})
            data['qty'] += q.quantity
            data['reserved'] += q.reserved_quantity or 0.0

        warehouses = self.env['stock.warehouse'].sudo().search([])
        rows = []
        total = 0.0
        for wh in warehouses:
            data = per_wh.get(wh.id, {'qty': 0.0, 'reserved': 0.0})
            available = data['qty'] - data['reserved']
            total += available
            rows.append({
                'company': wh.company_id.name or '',
                'warehouse': wh.name or '',
                'qty': data['qty'],
                'reserved': data['reserved'],
                'available': available,
            })
        rows.sort(key=lambda r: r['available'], reverse=True)
        return rows, total

    def _render_html(self, rows, product):
        uom = html.escape(product.uom_id.name or '')
        if not rows:
            return ('<p class="text-muted mb-0"><i class="fa fa-info-circle"/> '
                    'No hay almacenes configurados.</p>')
        body = ''
        for r in rows:
            color = '#198754' if r['available'] > 0.0 else '#999999'
            weight = '600' if r['available'] > 0.0 else '400'
            body += (
                '<tr style="border-bottom:1px solid #eee;">'
                f'<td style="padding:5px 8px;">{html.escape(r["company"])}</td>'
                f'<td style="padding:5px 8px;">{html.escape(r["warehouse"])}</td>'
                f'<td style="padding:5px 8px; text-align:right;">{r["qty"]:.2f}</td>'
                f'<td style="padding:5px 8px; text-align:right;">{r["reserved"]:.2f}</td>'
                f'<td style="padding:5px 8px; text-align:right; color:{color}; '
                f'font-weight:{weight};">{r["available"]:.2f}</td>'
                f'<td style="padding:5px 8px; color:#888;">{uom}</td>'
                '</tr>'
            )
        return (
            '<table style="width:100%; border-collapse:collapse; font-size:13px;">'
            '<thead><tr style="background:#f5f5f5; border-bottom:1px solid #ddd; color:#333;">'
            '<th style="padding:6px 8px; text-align:left;">Sucursal</th>'
            '<th style="padding:6px 8px; text-align:left;">Almacén</th>'
            '<th style="padding:6px 8px; text-align:right;">Físico</th>'
            '<th style="padding:6px 8px; text-align:right;">Reservado</th>'
            '<th style="padding:6px 8px; text-align:right;">Disponible</th>'
            '<th style="padding:6px 8px;">Unidad</th>'
            '</tr></thead>'
            f'<tbody>{body}</tbody></table>'
        )
