import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class StockProductBranchLocation(models.Model):
    """
    Ubicación habitual de un producto en un almacén/sucursal.

    Relaciona: Empresa + Almacén + Producto → Ubicación interna habitual.
    Se usa para asignar automáticamente la ubicación destino/origen en
    recepciones de compras y transferencias internas.
    """
    _name = 'stock.product.branch.location'
    _description = 'Ubicación de Producto por Sucursal'
    _order = 'company_id, warehouse_id, product_id'
    _check_company_auto = True

    # ─── Campos principales ─────────────────────────────────────────────────────

    company_id = fields.Many2one(
        'res.company',
        string='Empresa / Sucursal',
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén',
        required=True,
        index=True,
        domain="[('company_id', '=', company_id)]",
        check_company=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        index=True,
        domain="[('is_storable', '=', True)]",
    )
    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Plantilla de Producto',
        related='product_id.product_tmpl_id',
        store=True,
        readonly=True,
        index=True,
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Ubicación Habitual',
        required=True,
        domain="[('usage', '=', 'internal'), ('active', '=', True)]",
        check_company=True,
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
    )
    notes = fields.Text(
        string='Observaciones',
    )

    # ─── Restricción de unicidad ─────────────────────────────────────────────────

    _sql_constraints = [
        (
            'unique_product_company_warehouse',
            'UNIQUE(product_id, company_id, warehouse_id)',
            'Ya existe una configuración para este Producto + Empresa + Almacén. '
            'No se permiten duplicados.',
        ),
    ]

    # ─── Nombre para display ─────────────────────────────────────────────────────

    def _compute_display_name(self):
        for rec in self:
            parts = [
                rec.product_id.display_name or '?',
                rec.warehouse_id.name or '?',
                rec.location_id.display_name or '?',
            ]
            rec.display_name = ' / '.join(parts)

    # ─── Validaciones ────────────────────────────────────────────────────────────

    @api.constrains('location_id')
    def _check_location_usage(self):
        """La ubicación debe ser de tipo interno y no estar archivada."""
        for rec in self:
            if not rec.location_id:
                continue
            if not rec.location_id.active:
                raise ValidationError(
                    _('No se puede asignar la ubicación "%s" porque está archivada.')
                    % rec.location_id.complete_name
                )
            if rec.location_id.usage != 'internal':
                raise ValidationError(
                    _('La ubicación habitual debe ser de tipo "Interna". '
                      'La ubicación "%s" es de tipo "%s".')
                    % (rec.location_id.complete_name, rec.location_id.usage)
                )

    @api.constrains('location_id', 'warehouse_id')
    def _check_location_in_warehouse(self):
        """La ubicación debe pertenecer a la jerarquía del almacén."""
        for rec in self:
            if not rec.location_id or not rec.warehouse_id:
                continue
            view_loc = rec.warehouse_id.view_location_id
            if not view_loc:
                continue
            loc_path = rec.location_id.parent_path or ''
            wh_path = view_loc.parent_path or ''
            if wh_path and not loc_path.startswith(wh_path):
                raise ValidationError(
                    _('La ubicación "%(loc)s" no pertenece a la jerarquía del almacén "%(wh)s".\n'
                      'Seleccione una ubicación dentro de "%(view_loc)s".',
                      loc=rec.location_id.complete_name,
                      wh=rec.warehouse_id.name,
                      view_loc=view_loc.complete_name)
                )

    @api.constrains('location_id', 'company_id')
    def _check_location_company(self):
        """La ubicación no debe pertenecer a otra empresa."""
        for rec in self:
            if not rec.location_id or not rec.company_id:
                continue
            loc_company = rec.location_id.company_id
            if loc_company and loc_company.id != rec.company_id.id:
                raise ValidationError(
                    _('La ubicación "%(loc)s" pertenece a la empresa "%(loc_co)s", '
                      'no a "%(co)s". En un entorno multiempresa, use ubicaciones '
                      'de la misma empresa.',
                      loc=rec.location_id.complete_name,
                      loc_co=loc_company.name,
                      co=rec.company_id.name)
                )

    # ─── Onchange: filtrar ubicaciones por almacén ───────────────────────────────

    @api.onchange('warehouse_id')
    def _onchange_warehouse_id(self):
        """Limpiar ubicación si cambia el almacén."""
        if self.location_id and self.warehouse_id:
            view_loc = self.warehouse_id.view_location_id
            if view_loc:
                loc_path = self.location_id.parent_path or ''
                wh_path = view_loc.parent_path or ''
                if wh_path and not loc_path.startswith(wh_path):
                    self.location_id = False

    @api.onchange('company_id')
    def _onchange_company_id(self):
        """Limpiar almacén y ubicación si cambia la empresa."""
        if self.warehouse_id and self.warehouse_id.company_id != self.company_id:
            self.warehouse_id = False
            self.location_id = False
