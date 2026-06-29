import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockInventoryInitWizard(models.TransientModel):
    _name = 'stock.inventory.init.wizard'
    _description = 'Preparar Ajuste de Inventario desde Configuración'

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
    )
    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string='Almacenes',
        domain="[('company_id', '=', company_id)]",
        help='Dejar vacío para incluir todos los almacenes de la empresa seleccionada.',
    )

    # ── Contadores informativos ──────────────────────────────────────────────────

    config_count = fields.Integer(
        string='Configuraciones activas',
        compute='_compute_counts',
    )
    new_quant_count = fields.Integer(
        string='Quants nuevos a crear',
        compute='_compute_counts',
    )
    existing_quant_count = fields.Integer(
        string='Quants ya existentes',
        compute='_compute_counts',
    )

    @api.depends('company_id', 'warehouse_ids')
    def _compute_counts(self):
        for wiz in self:
            configs = wiz._get_configs()
            wiz.config_count = len(configs)
            existing = 0
            for cfg in configs:
                if self.env['stock.quant'].sudo().search_count([
                    ('product_id', '=', cfg.product_id.id),
                    ('location_id', '=', cfg.location_id.id),
                ]):
                    existing += 1
            wiz.existing_quant_count = existing
            wiz.new_quant_count = wiz.config_count - existing

    # ── Helpers ──────────────────────────────────────────────────────────────────

    def _get_configs(self):
        domain = [
            ('active', '=', True),
            ('company_id', '=', self.company_id.id),
        ]
        if self.warehouse_ids:
            domain.append(('warehouse_id', 'in', self.warehouse_ids.ids))
        return self.env['stock.product.branch.location'].search(domain)

    # ── Acción principal ─────────────────────────────────────────────────────────

    def action_prepare(self):
        self.ensure_one()
        configs = self._get_configs()
        if not configs:
            raise UserError(_(
                'No se encontraron configuraciones activas para los filtros seleccionados.'
            ))

        Quant = self.env['stock.quant'].sudo()
        quant_ids = []

        for cfg in configs:
            if not cfg.product_id or not cfg.location_id:
                continue

            quant = Quant.search([
                ('product_id', '=', cfg.product_id.id),
                ('location_id', '=', cfg.location_id.id),
            ], limit=1)

            if not quant:
                quant = Quant.with_context(inventory_mode=True).create({
                    'product_id': cfg.product_id.id,
                    'location_id': cfg.location_id.id,
                    'inventory_quantity': 0.0,
                })
                _logger.debug(
                    'SPLB Inventory: Quant creado para %s en %s',
                    cfg.product_id.display_name, cfg.location_id.complete_name,
                )
            else:
                # Marcar para conteo sin modificar la cantidad contada
                quant.write({'inventory_quantity_set': True})

            quant_ids.append(quant.id)

        if not quant_ids:
            raise UserError(_('No se pudo preparar ningún ajuste. Verifique la configuración.'))

        # Redirigir al Inventario Físico filtrado a estos quants
        action = self.env['stock.quant'].action_view_inventory()
        action['domain'] = [('id', 'in', quant_ids)]
        action['name'] = _('Inventario Físico — Desde Configuración SPLB')
        action['target'] = 'main'
        return action
