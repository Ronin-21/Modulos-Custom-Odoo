# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import UserError


class SaleOpFlowConfigWizard(models.TransientModel):
    _name = 'sale.op.flow.config.wizard'
    _description = 'Ajustes de Operaciones de Venta'

    # ── Cuentas contables para diferencias de caja ──────────────────────────
    use_payment_journal_for_differences = fields.Boolean(
        string='Usar diario del medio de pago para diferencias',
        default=True,
        help=(
            'Si está activo, cada diferencia se contabiliza en el mismo diario del medio rendido: '
            'Efectivo, Banco, Tarjeta, etc. Es el criterio recomendado. Si está desactivado, '
            'se usa el diario fallback configurado abajo.'
        ),
    )

    cash_difference_journal_id = fields.Many2one(
        'account.journal',
        string='Diario fallback para diferencias de caja',
        domain="[('type', 'in', ['cash', 'bank', 'credit', 'general'])]",
        help='Solo se usa si está desactivado "Usar diario del medio de pago" o si no se puede determinar el diario de la línea de rendición.',
    )
    cash_difference_loss_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de pérdida de caja',
        domain="[('account_type', 'in', ['expense', 'expense_direct_cost'])]",
        help='Cuenta de gastos para registrar faltantes de caja (lo que el cajero debe pero no rinde).',
    )
    cash_difference_gain_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de ganancia de caja',
        domain="[('account_type', 'in', ['income', 'income_other'])]",
        help='Cuenta de ingresos para registrar sobrantes de caja.',
    )

    allow_dispatch_without_stock = fields.Boolean(
        string='Permitir despacho sin stock',
        default=True,
        help=(
            'Si está activo, el botón Confirmar despacho puede validar la entrega '
            'aunque no haya stock reservado. Odoo registrará el movimiento de stock '
            'y podrá dejar stock negativo. Si está desactivado, el despacho exige '
            'disponibilidad/reserva antes de validar.'
        ),
    )

    auto_print_invoice = fields.Boolean(
        string='Imprimir factura automáticamente al confirmar cobro',
        default=False,
        help=(
            'Si está activo, al confirmar el cobro se abre directamente el PDF de la '
            'factura sin preguntar. Si está desactivado, se muestra un diálogo para '
            'elegir si imprimir o no.'
        ),
    )

    cash_rounding_id = fields.Many2one(
        'account.cash.rounding',
        string='Redondeo de cobros',
        help='Si está configurado, se aplica automáticamente a todas las facturas generadas desde el wizard de cobro.',
    )

    partner_autocomplete_enabled = fields.Boolean(
        string='Sugerir contactos de internet en búsqueda',
        default=False,
        help=(
            'Si está activo, al buscar un contacto en cualquier campo de Odoo se sugieren '
            'empresas desde la base de datos de Odoo (internet). '
            'Si está desactivado, solo se muestran contactos existentes en la base de datos local.'
        ),
    )

    quotation_validity_days = fields.Integer(
        string='Vigencia por defecto (días)',
        default=0,
        help=(
            'Cantidad de días de vigencia que se asigna automáticamente al crear un nuevo presupuesto. '
            'También se usa al renovar la vigencia con el botón "Renovar vigencia". '
            'Usar 0 para no asignar vigencia automática.'
        ),
    )
    expiry_warning_days = fields.Integer(
        string='Avisar con anticipación (días)',
        default=3,
        help='Cantidad de días antes del vencimiento para mostrar el estado "Por vencer" en el presupuesto.',
    )
    auto_cancel_expired = fields.Boolean(
        string='Cancelar presupuestos vencidos automáticamente',
        default=False,
        help=(
            'Si está activo, el cron diario cancelará los presupuestos SOF cuya vigencia '
            'ya expiró. Si está desactivado, los presupuestos vencidos permanecen abiertos '
            'pero se bloquea su confirmación.'
        ),
    )

    allow_cashier_cash_moves = fields.Boolean(
        string='Permitir ingresos/egresos de efectivo al Cajero',
        default=False,
        help=(
            'Si está activo, el rol Cajero puede registrar ingresos y egresos de efectivo en su sesión. '
            'El Supervisor siempre puede hacerlo, independientemente de esta opción.'
        ),
    )

    allow_cashier_exchange = fields.Boolean(
        string='Cajero puede hacer Cambio / Devolución',
        default=False,
        help=(
            'Si está activo, el rol Cajero ve y puede usar el botón "Cambio / Devolución". '
            'El Supervisor siempre puede, independientemente de esta opción.'
        ),
    )
    cashier_actions_require_pin = fields.Boolean(
        string='Exigir PIN de supervisor para NC y Cambios del cajero',
        default=False,
        help=(
            'Si está activo, cuando el Cajero use "Nota de Crédito" o "Cambio / Devolución" '
            'se pedirá el PIN de un supervisor antes de continuar. No aplica al Supervisor.'
        ),
    )

    product_search_limit = fields.Integer(
        string='Límite de resultados en búsqueda de productos',
        default=0,
        help=(
            'Cantidad máxima de productos a mostrar en el desplegable al buscar en líneas de pedido. '
            'Aplica a Ventas nativo y al flujo SOF. '
            'Usar 0 para dejar el comportamiento estándar de Odoo (sin límite adicional).'
        ),
    )

    partner_search_limit = fields.Integer(
        string='Límite de resultados en búsqueda de contactos',
        default=0,
        help=(
            'Cantidad máxima de contactos a mostrar en el desplegable al buscar un contacto/cliente. '
            'Aplica a cualquier campo de contacto en Odoo. '
            'Usar 0 para dejar el comportamiento estándar de Odoo (sin límite adicional).'
        ),
    )

    @staticmethod
    def _str_to_bool(value):
        return str(value).lower() in ('1', 'true', 't', 'yes', 'y', 'on', 'si', 'sí')

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        get = self.env['ir.config_parameter'].sudo().get_param

        res['allow_dispatch_without_stock'] = self._str_to_bool(
            get('sale_op_flow.allow_dispatch_without_stock', '1')
        )
        res['use_payment_journal_for_differences'] = self._str_to_bool(
            get('sale_op_flow.use_payment_journal_for_differences', '1')
        )
        res['auto_print_invoice'] = self._str_to_bool(
            get('sale_op_flow.auto_print_invoice', '0')
        )
        res['allow_cashier_cash_moves'] = self._str_to_bool(
            get('sale_op_flow.allow_cashier_cash_moves', '0')
        )
        res['allow_cashier_exchange'] = self._str_to_bool(
            get('sale_op_flow.allow_cashier_exchange', '0')
        )
        res['cashier_actions_require_pin'] = self._str_to_bool(
            get('sale_op_flow.cashier_actions_require_pin', '0')
        )
        res['partner_autocomplete_enabled'] = self._str_to_bool(
            get('sale_op_flow.partner_autocomplete_enabled', '0')
        )
        try:
            rid = int(get('sale_op_flow.cash_rounding_id', '0') or 0)
            res['cash_rounding_id'] = rid if rid > 0 else False
        except (ValueError, TypeError):
            res['cash_rounding_id'] = False
        try:
            res['product_search_limit'] = int(get('sale_op_flow.product_search_limit', '0') or 0)
        except (ValueError, TypeError):
            res['product_search_limit'] = 0
        try:
            res['partner_search_limit'] = int(get('sale_op_flow.partner_search_limit', '0') or 0)
        except (ValueError, TypeError):
            res['partner_search_limit'] = 0
        try:
            res['quotation_validity_days'] = int(get('sale_op_flow.quotation_validity_days', '0') or 0)
        except (ValueError, TypeError):
            res['quotation_validity_days'] = 0
        try:
            res['expiry_warning_days'] = int(get('sale_op_flow.expiry_warning_days', '3') or 3)
        except (ValueError, TypeError):
            res['expiry_warning_days'] = 3
        res['auto_cancel_expired'] = self._str_to_bool(
            get('sale_op_flow.auto_cancel_expired', '0')
        )
        # Leer cuentas y diario guardados.
        for fname in ('cash_difference_journal_id',
                      'cash_difference_loss_account_id',
                      'cash_difference_gain_account_id'):
            try:
                val = int(get(f'sale_op_flow.{fname}', '0') or 0)
                res[fname] = val if val > 0 else False
            except (ValueError, TypeError):
                res[fname] = False

        # Fallback tipo POS: si hay diario configurado y trae cuentas de pérdida/ganancia,
        # mostrarlas aunque todavía no existan en ir.config_parameter.
        journal = self.env['account.journal'].browse(res.get('cash_difference_journal_id') or 0)
        if journal.exists():
            if not res.get('cash_difference_loss_account_id') and 'loss_account_id' in journal._fields and journal.loss_account_id:
                res['cash_difference_loss_account_id'] = journal.loss_account_id.id
            if not res.get('cash_difference_gain_account_id') and 'profit_account_id' in journal._fields and journal.profit_account_id:
                res['cash_difference_gain_account_id'] = journal.profit_account_id.id
        return res

    def action_save(self):
        self.ensure_one()
        if not self.use_payment_journal_for_differences and not self.cash_difference_journal_id:
            raise UserError(_('Si no usás el diario del medio de pago, debés configurar un diario fallback para diferencias.'))

        if self.cash_difference_journal_id:
            if not self.cash_difference_journal_id.default_account_id:
                raise UserError(_('El diario fallback para diferencias debe tener una cuenta por defecto.'))
            if self.cash_difference_journal_id.company_id and self.cash_difference_journal_id.company_id != self.env.company:
                raise UserError(_('El diario fallback para diferencias pertenece a otra empresa.'))

        set_param = self.env['ir.config_parameter'].sudo().set_param

        set_param('sale_op_flow.allow_dispatch_without_stock',
                  '1' if self.allow_dispatch_without_stock else '0')
        set_param('sale_op_flow.use_payment_journal_for_differences',
                  '1' if self.use_payment_journal_for_differences else '0')
        set_param('sale_op_flow.auto_print_invoice',
                  '1' if self.auto_print_invoice else '0')
        set_param('sale_op_flow.allow_cashier_cash_moves',
                  '1' if self.allow_cashier_cash_moves else '0')
        set_param('sale_op_flow.allow_cashier_exchange',
                  '1' if self.allow_cashier_exchange else '0')
        set_param('sale_op_flow.cashier_actions_require_pin',
                  '1' if self.cashier_actions_require_pin else '0')
        set_param('sale_op_flow.partner_autocomplete_enabled',
                  '1' if self.partner_autocomplete_enabled else '0')
        set_param('sale_op_flow.cash_rounding_id',
                  str(self.cash_rounding_id.id) if self.cash_rounding_id else '0')
        set_param('sale_op_flow.product_search_limit',
                  str(max(0, self.product_search_limit or 0)))
        set_param('sale_op_flow.partner_search_limit',
                  str(max(0, self.partner_search_limit or 0)))
        set_param('sale_op_flow.quotation_validity_days',
                  str(max(0, self.quotation_validity_days or 0)))
        set_param('sale_op_flow.expiry_warning_days',
                  str(max(1, self.expiry_warning_days or 3)))
        set_param('sale_op_flow.auto_cancel_expired',
                  '1' if self.auto_cancel_expired else '0')

        # Guardar cuentas y diario como IDs en config_parameter.
        for fname in ('cash_difference_journal_id',
                      'cash_difference_loss_account_id',
                      'cash_difference_gain_account_id'):
            val = getattr(self, fname)
            set_param(f'sale_op_flow.{fname}', str(val.id) if val else '0')

        # Sincronizar además el diario fallback, igual que POS usa loss/profit_account_id
        # del journal para diferencias. Las diferencias normales usan el diario del
        # medio de pago y toman estas cuentas globales al momento de contabilizar.
        journal = self.cash_difference_journal_id.sudo()
        vals = {}
        if journal and 'loss_account_id' in journal._fields:
            vals['loss_account_id'] = self.cash_difference_loss_account_id.id or False
        if journal and 'profit_account_id' in journal._fields:
            vals['profit_account_id'] = self.cash_difference_gain_account_id.id or False
        if vals:
            journal.write(vals)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Ajustes guardados'),
                'message': _('Configuración guardada correctamente.'),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
