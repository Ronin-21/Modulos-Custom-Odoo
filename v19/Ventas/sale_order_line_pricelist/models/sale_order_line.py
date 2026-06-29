from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    line_pricelist_id = fields.Many2one(
        comodel_name='product.pricelist',
        string='Lista de Precio de Línea',
        copy=True,
        help=(
            'Si se selecciona, esta lista de precios se usará solo para esta línea. '
            'Si está vacía, se usará la lista de precios de la orden.'
        ),
    )

    # ========== HELPER ==========

    def _get_effective_pricelist(self):
        """Devuelve la lista de precios efectiva: la de la línea si existe, sino la de la orden."""
        self.ensure_one()
        return self.line_pricelist_id or self.order_id.pricelist_id

    # ========== COMPUTE OVERRIDES ==========

    @api.depends('product_id', 'product_uom_id', 'product_uom_qty', 'line_pricelist_id')
    def _compute_pricelist_item_id(self):
        """Extiende el cálculo estándar usando la lista de precios efectiva de la línea."""
        for line in self:
            if not line.product_id or line.display_type:
                line.pricelist_item_id = False
                continue
            effective_pricelist = line._get_effective_pricelist()
            if not effective_pricelist:
                line.pricelist_item_id = False
                continue
            line.pricelist_item_id = effective_pricelist._get_product_rule(
                product=line.product_id,
                **line._get_pricelist_kwargs(),
            )

    @api.depends('product_id', 'product_uom_id', 'product_uom_qty', 'line_pricelist_id')
    def _compute_price_unit(self):
        """
        Extiende el cálculo del precio unitario.
        Las líneas con lista de precios propia siempre recalculan (fuerza bypass del guard manual),
        ya que la lista de precios de la línea es la fuente de verdad del precio.
        """
        lines_with_own_pl = self.filtered('line_pricelist_id')
        remaining = self - lines_with_own_pl
        if lines_with_own_pl:
            super(SaleOrderLine, lines_with_own_pl.with_context(
                force_price_recomputation=True
            ))._compute_price_unit()
        if remaining:
            super(SaleOrderLine, remaining)._compute_price_unit()

    @api.depends('product_id', 'product_uom_id', 'product_uom_qty', 'line_pricelist_id')
    def _compute_discount(self):
        """
        Extiende el cálculo del descuento para que el guard use la lista de precios efectiva
        (la propia de la línea si existe, sino la de la orden).
        """
        discount_enabled = self.env['product.pricelist.item']._is_discount_feature_enabled()
        for line in self:
            if not line.product_id or line.display_type:
                line.discount = 0.0
                continue

            # Usa la lista de precios efectiva en lugar de solo order_id.pricelist_id
            if not (line._get_effective_pricelist() and discount_enabled):
                continue

            if line.combo_item_id:
                line.discount = line._get_linked_line().discount
                continue

            line.discount = 0.0

            if not line.pricelist_item_id._show_discount():
                continue

            line = line.with_company(line.company_id)
            pricelist_price = line._get_pricelist_price()
            base_price = line._get_pricelist_price_before_discount()

            if base_price != 0:
                discount = (base_price - pricelist_price) / base_price * 100
                if (discount > 0 and base_price > 0) or (discount < 0 and base_price < 0):
                    line.discount = discount

    # ========== ONCHANGE ==========

    @api.onchange('line_pricelist_id')
    def _onchange_line_pricelist_id(self):
        """Recalcula precio y descuento inmediatamente en la UI al cambiar la lista de línea."""
        if not self.product_id:
            return
        # Fuerza recomputación de pricelist_item_id (campo no almacenado)
        self.invalidate_recordset(['pricelist_item_id'])
        # Resetea precio usando la lista efectiva; skip_price_unit_lock evita bloqueo en onchange
        self.with_context(
            sale_write_from_compute=True,
            skip_price_unit_lock=True,
        )._reset_price_unit()
        self.discount = 0.0
        self._compute_discount()

    # ========== CRUD ==========

    def write(self, vals):
        # Bloqueo de precio manual para usuarios no administradores.
        # Se permite escritura si viene del motor de cómputo (sale_write_from_compute)
        # o de un recálculo interno del módulo (skip_price_unit_lock).
        if (
            'price_unit' in vals
            and not self.env.context.get('sale_write_from_compute')
            and not self.env.context.get('skip_price_unit_lock')
        ):
            is_admin = (
                self.env.user.has_group('sales_team.group_sale_manager')
                or self.env.user.has_group('base.group_system')
            )
            if not is_admin:
                raise UserError(_(
                    'No puede modificar manualmente el precio unitario. '
                    'Debe cambiar la lista de precios o solicitar autorización a un administrador.'
                ))

        # Captura estado anterior de line_pricelist_id para el chatter
        pricelist_changes = {}
        if (
            'line_pricelist_id' in vals
            and not self.env.context.get('skip_pricelist_chatter')
        ):
            new_pricelist_id = vals.get('line_pricelist_id') or False
            for line in self:
                old_id = line.line_pricelist_id.id or False
                if old_id != (new_pricelist_id or False):
                    pricelist_changes[line.id] = line.line_pricelist_id

        result = super().write(vals)

        # Publica mensajes en el chatter después del write (valores ya actualizados)
        if pricelist_changes:
            for line in self.filtered(lambda l: l.id in pricelist_changes):
                line._log_pricelist_change(pricelist_changes[line.id])

        return result

    # ========== CHATTER ==========

    def _log_pricelist_change(self, old_pricelist):
        """Publica un mensaje en el chatter de la orden cuando cambia la lista de línea."""
        self.ensure_one()
        if not self.product_id or not self.order_id:
            return
        product_name = self.product_id.display_name
        new_pricelist = self.line_pricelist_id
        price_info = f'{self.price_unit:.2f} {self.currency_id.name}'

        if not old_pricelist and new_pricelist:
            body = _(
                'La línea del producto "%(product)s" tiene ahora una lista de precios individual: '
                '"%(new)s". Precio recalculado: %(price)s.',
                product=product_name,
                new=new_pricelist.name,
                price=price_info,
            )
        elif old_pricelist and not new_pricelist:
            order_pl_name = self.order_id.pricelist_id.name or _('ninguna')
            body = _(
                'La línea del producto "%(product)s" ya no tiene lista de precios individual. '
                'Vuelve a usar la lista general "%(order_pl)s". Precio recalculado: %(price)s.',
                product=product_name,
                order_pl=order_pl_name,
                price=price_info,
            )
        else:
            body = _(
                'La línea del producto "%(product)s" cambió su lista de precios individual de '
                '"%(old)s" a "%(new)s". Precio recalculado: %(price)s.',
                product=product_name,
                old=old_pricelist.name,
                new=new_pricelist.name,
                price=price_info,
            )
        self.order_id.message_post(body=body)

    # ========== FACTURACIÓN ==========

    def _prepare_invoice_line(self, **optional_values):
        """Copia la lista de precios de la línea a la línea de factura (para trazabilidad)."""
        res = super()._prepare_invoice_line(**optional_values)
        if self.line_pricelist_id:
            res['sale_line_pricelist_id'] = self.line_pricelist_id.id
        return res
