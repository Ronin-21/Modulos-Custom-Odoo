from odoo import fields, models, _


class ResConfigSettings(models.TransientModel):
    """
    Extiende los ajustes de configuración para incluir opciones
    del módulo Ubicaciones de Producto por Sucursal.
    """
    _inherit = 'res.config.settings'

    # ─── Activación por tipo de operación ────────────────────────────────────────

    splb_apply_on_receipts = fields.Boolean(
        string='Aplicar en recepciones de compra',
        help=(
            'Al confirmar un albarán de recepción, asigna automáticamente la '
            'ubicación de destino configurada para cada producto en el almacén.'
        ),
        config_parameter='stock_product_location_by_branch.apply_on_receipts',
        default=True,
    )
    splb_apply_on_internals = fields.Boolean(
        string='Aplicar en transferencias internas',
        help=(
            'Al confirmar una transferencia interna, asigna automáticamente las '
            'ubicaciones de origen y destino según la configuración por producto '
            'y almacén.'
        ),
        config_parameter='stock_product_location_by_branch.apply_on_internals',
        default=True,
    )

    # ─── Comportamiento si falta configuración ───────────────────────────────────

    splb_missing_config_mode = fields.Selection(
        selection=[
            ('warn', 'Permitir y mostrar advertencia en el albarán'),
            ('block', 'Bloquear: no permitir confirmar si falta configuración'),
        ],
        string='Si falta configuración de ubicación',
        help=(
            'Define qué hace el sistema cuando un producto no tiene ubicación '
            'habitual configurada para el almacén correspondiente:\n'
            '- Advertencia: deja la ubicación estándar y registra un aviso.\n'
            '- Bloquear: impide confirmar el albarán hasta completar la configuración.'
        ),
        config_parameter='stock_product_location_by_branch.missing_config_mode',
        default='warn',
    )

    # ─── Opciones adicionales ─────────────────────────────────────────────────────

    splb_apply_on_move_lines = fields.Boolean(
        string='Aplicar también en líneas de operación (detalle)',
        help=(
            'Además de actualizar el movimiento (stock.move), también actualiza '
            'las líneas de operación detalladas (stock.move.line) que estén pendientes.'
        ),
        config_parameter='stock_product_location_by_branch.apply_on_move_lines',
        default=True,
    )
