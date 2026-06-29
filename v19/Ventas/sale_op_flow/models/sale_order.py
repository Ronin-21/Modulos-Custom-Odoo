# -*- coding: utf-8 -*-
"""
sale.order — Extensión operativa v2

Estados operativos:
  quotation  → Presupuesto (puede esperar indefinidamente)
  confirmed  → Confirmado: factura borrador creada, cajero puede cobrar,
               despacho puede PREPARAR (no entregar)
  paid       → Pagado: factura cobrada, despacho puede ENTREGAR
  dispatched → Despachado: entrega validada, ciclo cerrado
  cancelled  → Cancelado

El vendedor necesita una sesión de caja activa para crear presupuestos.
Al confirmar, el pedido pasa automáticamente a la cola del cajero.
NO existe el botón "Enviar a Caja" — la confirmación lo hace.
"""
from datetime import timedelta

from odoo import models, fields, api, Command, _
from odoo.exceptions import UserError, AccessError

OPERATIONAL_STATES = [
    ('quotation', 'Presupuesto'),
    ('confirmed', 'Confirmado'),
    ('prepared', 'Preparado'),   # Despacho preparó, esperando pago o ya pagado
    ('paid', 'Pagado'),
    ('in_delivery', 'En reparto'),  # Salió con flete, pendiente confirmación de recepción
    ('dispatched', 'Despachado'),
    ('cancelled', 'Cancelado'),
]


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    operational_state = fields.Selection(
        OPERATIONAL_STATES,
        string='Pedido',
        default='quotation',
        required=True,
        tracking=True,
        index=True,
        copy=False,
    )
    proposed_payment_journal_id = fields.Many2one(
        'account.journal',
        string='Medio de pago sugerido',
        domain="[('type', 'in', ['bank', 'cash'])]",
        tracking=True,
    )
    final_payment_journal_id = fields.Many2one(
        'account.journal',
        string='Medio de pago final',
        domain="[('type', 'in', ['bank', 'cash'])]",
        tracking=True,
        copy=False,
    )
    financing_plan_id = fields.Many2one(
        'sale.financing.plan',
        string='Plan de pago',
        domain="[('active', '=', True)]",
        tracking=True,
        copy=False,
    )
    adjustment_type = fields.Selection(
        [('none', 'Sin ajuste'), ('discount', 'Descuento'), ('surcharge', 'Recargo')],
        string='Tipo de ajuste',
        compute='_compute_adjustment_from_plan',
        store=True,    # store=True + readonly=True: ORM siempre recomputa al cambiar dependencia
        readonly=True, # readonly=True impide escritura manual → ORM nunca preserva valor viejo
        copy=False,
    )
    adjustment_rate = fields.Float(
        string='% Ajuste',
        digits=(5, 2),
        compute='_compute_adjustment_from_plan',
        store=True,
        readonly=True,
        copy=False,
    )
    adjustment_amount = fields.Monetary(
        string='Monto de ajuste',
        compute='_compute_adjustment_amount',
        store=True,
        readonly=True,
        currency_field='currency_id',
    )
    amount_with_adjustment = fields.Monetary(
        string='Total estimado c/ajuste',
        compute='_compute_adjustment_amount',
        store=True,
        readonly=True,
        currency_field='currency_id',
    )
    amount_per_installment = fields.Monetary(
        string='Valor por cuota',
        compute='_compute_adjustment_amount',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help='Monto estimado de cada cuota, incluyendo el recargo.',
    )
    cashier_session_id = fields.Many2one(
        'sale.cashier.session',
        string='Sesión de caja',
        copy=False,
        tracking=True,
        readonly=True,
    )
    # Trazabilidad
    confirmed_by = fields.Many2one('res.users', string='Confirmado por', copy=False, readonly=True)
    confirmed_date = fields.Datetime(string='Fecha confirmación', copy=False, readonly=True)
    collected_by = fields.Many2one('res.users', string='Cobrado por', copy=False, tracking=True, readonly=True)
    collected_date = fields.Datetime(string='Fecha de cobro', copy=False, readonly=True)
    is_credit_sale = fields.Boolean(
        string='Venta en Cuenta Corriente', copy=False, readonly=True,
        help='Marcado cuando el cajero registra la venta a crédito (CC). '
             'La factura queda pendiente de cobro posterior.',
    )
    dispatched_by = fields.Many2one('res.users', string='Despachado por', copy=False, tracking=True, readonly=True)
    dispatched_date = fields.Datetime(string='Fecha de despacho', copy=False, readonly=True)
    dispatch_notes = fields.Text(string='Notas de despacho', copy=False)
    delivery_date = fields.Date(
        string='Fecha de entrega',
        copy=False,
        tracking=True,
        help='Fecha programada para la entrega a domicilio.',
    )
    delivery_shift = fields.Selection(
        [('morning', 'Mañana'), ('afternoon', 'Tarde')],
        string='Turno de entrega',
        copy=False,
        tracking=True,
    )
    dispatch_prepared = fields.Boolean(
        string='Despacho preparado',
        copy=False,
        tracking=True,
        readonly=True,
        help='Indica que el equipo de despacho preparó o reservó la entrega desde el flujo operativo.',
    )
    dispatch_prepared_by = fields.Many2one(
        'res.users',
        string='Preparado por',
        copy=False,
        readonly=True,
    )
    dispatch_prepared_date = fields.Datetime(
        string='Fecha de preparación',
        copy=False,
        readonly=True,
    )

    is_sof_order = fields.Boolean(
        string='Flujo Operativo',
        default=False,
        copy=False,
        index=True,
        help='Indica que este pedido usa el flujo operativo SOF (Vendedor → Caja → Despacho).',
    )

    sof_consumer_name = fields.Char(
        string='Nombre y Apellido',
        help='Nombre del comprador para identificar la cotización. Opcional, '
             'pensado sobre todo para ventas a consumidor final.',
    )
    sof_invoice_preference = fields.Selection([
        ('factura', 'Factura'),
        ('remito', 'Remito'),
    ], string='Comprobante solicitado',
       help='Indicación interna para el cajero sobre qué comprobante pidió el cliente. '
            'No afecta la facturación: es solo informativo.')

    # Visibilidad config-driven del botón Cambio/Devolución para el cajero.
    # Supervisor: siempre. Cajero: solo si el check de Ajustes está activo.
    sof_can_do_exchange = fields.Boolean(compute='_compute_sof_cashier_actions')

    # Tipo de comprobante realmente emitido (FACTURA A/B/C), leído de la factura posteada.
    sof_invoice_doc_type_name = fields.Char(
        string='Comprobante', compute='_compute_sof_invoice_doc_type', store=False,
    )

    @api.depends('invoice_ids', 'invoice_ids.state')
    def _compute_sof_invoice_doc_type(self):
        for order in self:
            name = False
            inv = order.invoice_ids.filtered(
                lambda i: i.move_type == 'out_invoice' and i.state == 'posted'
            )[:1]
            if inv and 'l10n_latam_document_type_id' in inv._fields and inv.l10n_latam_document_type_id:
                name = inv.l10n_latam_document_type_id.display_name
            order.sof_invoice_doc_type_name = name

    # Devolución total: todos los artículos facturados volvieron y no quedó reemplazo.
    sof_fully_returned = fields.Boolean(
        string='Devuelto totalmente', compute='_compute_sof_return_status', store=False,
    )

    @api.depends('exchange_ids', 'exchange_ids.state', 'invoice_ids', 'invoice_ids.state')
    def _compute_sof_return_status(self):
        for order in self:
            invoiced = 0.0
            for inv in order.invoice_ids.filtered(
                lambda i: i.move_type == 'out_invoice' and i.state == 'posted'
            ):
                invoiced += sum(inv.invoice_line_ids.filtered(
                    lambda l: l.display_type == 'product'
                ).mapped('quantity'))
            done = order.exchange_ids.filtered(lambda e: e.state == 'done')
            returned = sum(done.mapped('return_line_ids.quantity'))
            replaced = sum(done.mapped('new_line_ids.quantity'))
            order.sof_fully_returned = bool(invoiced) and returned >= invoiced - 0.001 and replaced <= 0.001

    @staticmethod
    def _sof_str_to_bool(value):
        return str(value).lower() in ('1', 'true', 't', 'yes', 'y', 'on', 'si', 'sí')

    @api.depends_context('uid')
    def _compute_sof_cashier_actions(self):
        user = self.env.user
        is_supervisor = user.has_group('sale_op_flow.group_sale_supervisor')
        is_cashier = user.has_group('sale_op_flow.group_sale_cashier')
        get = self.env['ir.config_parameter'].sudo().get_param
        can_ex = is_supervisor or (is_cashier and self._sof_str_to_bool(
            get('sale_op_flow.allow_cashier_exchange', '0')))
        for order in self:
            order.sof_can_do_exchange = can_ex

    sof_validity_status = fields.Selection([
        ('valid', 'Vigente'),
        ('expiring', 'Por vencer'),
        ('expired', 'Vencido'),
    ], string='Vigencia', compute='_compute_sof_validity_status', store=False)

    exchange_ids = fields.One2many('sale.exchange', 'order_id', string='Cambios / Devoluciones', copy=False)
    exchange_count = fields.Integer(compute='_compute_exchange_count', string='Cambios', store=False)

    @api.depends('exchange_ids')
    def _compute_exchange_count(self):
        for order in self:
            order.exchange_count = len(order.exchange_ids)

    # Campos computados para controlar visibilidad de smart buttons según rol y flujo
    sof_show_invoice_button = fields.Boolean(
        string='Ver factura',
        compute='_compute_sof_show_buttons',
        store=False,
    )
    sof_show_delivery_button = fields.Boolean(
        string='Ver entrega',
        compute='_compute_sof_show_buttons',
        store=False,
    )

    is_service_order = fields.Boolean(
        string='Orden de servicio',
        compute='_compute_is_service_order',
        store=False,
    )
    sof_service_label = fields.Char(
        string='Tipo',
        compute='_compute_is_service_order',
        store=False,
    )

    def init(self):
        """Sincroniza pedidos ya confirmados que quedaron con estado operativo viejo.

        En algunas bases, por actualizaciones anteriores o cambios manuales del statusbar,
        puede quedar state='sale'/'done' pero operational_state='quotation'. En ese caso
        Odoo ya no muestra el botón Confirmar porque la venta estándar ya está confirmada,
        pero nuestro flujo operativo sigue viéndola como Presupuesto. Al actualizar el
        módulo, los casos existentes pasan a Confirmado para que entren en Caja/Despacho.
        """
        super().init()
        # Primero marcar is_sof_order para no tocar ventas nativas en los pasos siguientes.
        self.env.cr.execute("""
            UPDATE sale_order
               SET is_sof_order = TRUE
             WHERE COALESCE(is_sof_order, FALSE) = FALSE
               AND cashier_session_id IS NOT NULL
        """)
        # Solo sincronizar operational_state en pedidos SOF que quedaron desfasados.
        self.env.cr.execute("""
            UPDATE sale_order
               SET operational_state = 'confirmed',
                   confirmed_by = COALESCE(confirmed_by, user_id),
                   confirmed_date = COALESCE(confirmed_date, write_date, date_order, create_date, NOW())
             WHERE is_sof_order = TRUE
               AND state IN ('sale', 'done')
               AND COALESCE(operational_state, 'quotation') = 'quotation'
        """)
        # Limpiar ventas nativas que pudieron haber recibido operational_state por versiones
        # anteriores del init() que no filtraba por is_sof_order.
        self.env.cr.execute("""
            UPDATE sale_order
               SET operational_state = 'quotation'
             WHERE COALESCE(is_sof_order, FALSE) = FALSE
               AND operational_state IS NOT NULL
               AND operational_state != 'quotation'
        """)

    # ── Computes ──────────────────────────────────────────────────────────────

    @api.depends('financing_plan_id', 'financing_plan_id.adjustment_type', 'financing_plan_id.adjustment_rate')
    def _compute_adjustment_from_plan(self):
        for order in self:
            plan = order.financing_plan_id
            if plan:
                order.adjustment_type = plan.adjustment_type
                order.adjustment_rate = plan.adjustment_rate
            else:
                order.adjustment_type = 'none'
                order.adjustment_rate = 0.0

    @api.depends('amount_untaxed', 'amount_total',
                 'financing_plan_id', 'financing_plan_id.adjustment_type',
                 'financing_plan_id.adjustment_rate', 'financing_plan_id.installments')
    def _compute_adjustment_amount(self):
        for order in self:
            # Leer el plan directamente en lugar de depender de campos non-stored
            # Esto evita la cadena non-stored → non-stored que falla en Odoo 19
            plan = order.financing_plan_id
            adj_type = plan.adjustment_type if plan else 'none'
            adj_rate = plan.adjustment_rate if plan else 0.0

            if adj_type == 'none' or not adj_rate:
                order.adjustment_amount = 0.0
            elif adj_type == 'discount':
                order.adjustment_amount = -(order.amount_untaxed * adj_rate / 100.0)
            else:
                order.adjustment_amount = order.amount_untaxed * adj_rate / 100.0
            order.amount_with_adjustment = order.amount_total + order.adjustment_amount
            # Monto por cuota
            installments = plan.installments if plan and plan.installments > 1 else 1
            if installments > 1:
                order.amount_per_installment = order.amount_with_adjustment / installments
            else:
                order.amount_per_installment = 0.0

    @api.onchange('financing_plan_id')
    def _onchange_financing_plan(self):
        """El plan es la fuente de verdad: al elegir un plan, el diario se deriva de él."""
        for order in self:
            plan = order.financing_plan_id
            if plan and plan.payment_journal_id:
                order.proposed_payment_journal_id = plan.payment_journal_id
            elif not plan:
                order.proposed_payment_journal_id = False

    # ── Override: create — verificar sesión abierta ────────────────────────

    # ── Columnas de estado separadas para la vista lista ──────────────────

    sof_pedido_estado = fields.Selection([
        ('presupuesto', 'Presupuesto'),
        ('confirmado', 'Confirmado'),
        ('ordenado', 'Ordenado'),       # Cobrado con diario NO fiscal (sin ARCA)
        ('facturado', 'Facturado'),     # Cobrado con diario fiscal (ARCA)
        ('cancelado', 'Cancelado'),
    ], string='Pedido', compute='_compute_sof_estado_cols', store=False)

    sof_cobro_estado = fields.Selection([
        ('na', 'N/A'),
        ('por_cobrar', 'Por cobrar'),
        ('pagado', 'Pagado'),
        ('cancelado', 'Cancelado'),
        ('nota_credito', 'Nota de crédito'),
    ], string='Factura', compute='_compute_sof_estado_cols', store=False)

    sof_entrega_estado = fields.Selection([
        ('na', 'N/A'),
        ('pendiente', 'Pendiente'),
        ('preparado', 'Preparado'),
        ('listo', 'Listo p/entregar'),
        ('parcial', 'Parcial'),
        ('en_reparto', 'En reparto'),
        ('entregado', 'Entregado'),
        ('cancelado', 'Cancelado'),
        ('devuelto', 'Devuelto'),       # Futuro: flujo de devoluciones
    ], string='Despacho', compute='_compute_sof_estado_cols', store=False)


    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'validity_date' in fields_list and self.env.context.get('default_is_sof_order'):
            try:
                days = int(self.env['ir.config_parameter'].sudo().get_param(
                    'sale_op_flow.quotation_validity_days', '0') or 0)
            except (ValueError, TypeError):
                days = 0
            if days > 0:
                res['validity_date'] = fields.Date.today() + timedelta(days=days)
        return res

    def copy(self, default=None):
        """Al duplicar un pedido SOF, el duplicado también es SOF, arranca como Presupuesto
        y queda asignado a la sesión de caja abierta actual."""
        default = dict(default or {})
        if self.is_sof_order:
            default.setdefault('is_sof_order', True)
            if not default.get('cashier_session_id'):
                session = self.env['sale.cashier.session'].search([
                    ('state', '=', 'open'),
                    ('company_id', '=', self.company_id.id),
                ], limit=1)
                if not session:
                    session = self.env['sale.cashier.session'].search(
                        [('state', '=', 'open')], limit=1
                    )
                if session:
                    default['cashier_session_id'] = session.id
        return super().copy(default)

    @api.model_create_multi
    def create(self, vals_list):
        """
        Bloquea la creación de presupuestos SOF si no hay sesión de caja abierta.
        Solo aplica cuando el pedido se crea desde el flujo SOF (is_sof_order=True en vals
        o default_is_sof_order=True en contexto). Pedidos nativos de Odoo no son bloqueados.
        """
        user = self.env.user
        is_sof_user = (
            user.has_group('sale_op_flow.group_sale_vendor')
            or user.has_group('sale_op_flow.group_sale_cashier')
            or user.has_group('sale_op_flow.group_sale_supervisor')
        )
        creating_sof = (
            self.env.context.get('default_is_sof_order')
            or any(v.get('is_sof_order') for v in vals_list)
        )
        if is_sof_user and creating_sof:
            Session = self.env['sale.cashier.session'].sudo()
            open_session = Session.search([
                ('state', '=', 'open'),
                ('company_id', '=', self.env.company.id),
            ], limit=1)
            if not open_session:
                open_session = Session.search([('state', '=', 'open')], limit=1)
            if not open_session:
                raise UserError(
                    _('⚠️ No hay ninguna sesión de caja abierta.\n\n'
                      'Antes de crear un presupuesto, el cajero debe abrir '
                      'la sesión del día desde:\n'
                      'Caja → Sesiones Abiertas → Nuevo\n\n'
                      'Una vez abierta la sesión podés crear presupuestos.')
                )
        return super().create(vals_list)


    def action_open_quick_customer_wizard(self):
        """Abre el wizard simplificado de creación de cliente."""
        self.ensure_one()
        return {
            'name': _('Nuevo Cliente'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.quick.customer.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_sale_order_id': self.id},
        }

    def write(self, vals):
        """Evita que el estado operativo quede desfasado del estado real de Odoo.

        Caso detectado: una venta ya está en state='sale' (Odoo la considera Orden de venta),
        pero operational_state queda o vuelve a 'quotation'. Entonces el botón Confirmar no
        aparece porque para Odoo ya está confirmada, y tampoco aparece Registrar Cobro porque
        para el flujo operativo sigue como Presupuesto.
        """
        res = super().write(vals)
        if not self.env.context.get('sof_skip_operational_sync'):
            to_sync = self.filtered(
                lambda order: order.is_sof_order
                and order.state in ('sale', 'done')
                and order.operational_state == 'quotation'
            )
            now = fields.Datetime.now()
            for order in to_sync:
                sync_vals = {'operational_state': 'confirmed'}
                if not order.confirmed_by:
                    sync_vals['confirmed_by'] = self.env.uid
                if not order.confirmed_date:
                    sync_vals['confirmed_date'] = now
                order.with_context(sof_skip_operational_sync=True).write(sync_vals)
        return res

    # ── Override: action_confirm ───────────────────────────────────────────

    @api.depends(
        'is_sof_order',
        'operational_state', 'state', 'dispatch_prepared',
        'final_payment_journal_id', 'final_payment_journal_id.l10n_ar_is_pos',
        'final_payment_journal_id.l10n_ar_afip_pos_system',
        'invoice_ids.state', 'invoice_ids.payment_state', 'invoice_ids.move_type',
        'picking_ids.state', 'picking_ids.picking_type_code',
    )
    def _compute_sof_estado_cols(self):
        """Calcula los 3 estados separados para las columnas Pedido/Factura/Despacho."""
        for order in self:
            if not order.is_sof_order:
                order.sof_pedido_estado = False
                order.sof_cobro_estado = False
                order.sof_entrega_estado = False
                continue
            op = order.operational_state
            # Si Odoo cancela via flujo nativo (state='cancel'), tomarlo como cancelado
            is_cancelled = (op == 'cancelled' or order.state == 'cancel')

            # ── PEDIDO: estado fiscal/administrativo ──────────────────────────
            if is_cancelled:
                order.sof_pedido_estado = 'cancelado'
            elif op == 'quotation':
                order.sof_pedido_estado = 'presupuesto'
            elif op in ('confirmed', 'prepared'):
                order.sof_pedido_estado = 'confirmado'
            elif op in ('paid', 'dispatched'):
                # Diario fiscal = usa documentos ARCA (l10n_ar_is_pos = True)
                journal = order.final_payment_journal_id
                is_fiscal = (
                    journal
                    and getattr(journal, 'l10n_ar_is_pos', False)
                )
                order.sof_pedido_estado = 'facturado' if is_fiscal else 'ordenado'
            else:
                order.sof_pedido_estado = 'presupuesto'

            # ── FACTURA: estado del cobro / factura contable ──────────────────
            out_invoices = order.invoice_ids.filtered(
                lambda i: i.move_type == 'out_invoice'
            )
            credit_notes = order.invoice_ids.filtered(
                lambda i: i.move_type == 'out_refund' and i.state != 'cancel'
            )

            if is_cancelled:
                order.sof_cobro_estado = 'cancelado'
            elif op == 'quotation':
                order.sof_cobro_estado = 'na'
            elif op in ('confirmed', 'prepared'):
                order.sof_cobro_estado = 'por_cobrar'
            elif op in ('paid', 'dispatched'):
                if credit_notes:
                    order.sof_cobro_estado = 'nota_credito'
                elif out_invoices and all(i.state == 'cancel' for i in out_invoices):
                    order.sof_cobro_estado = 'cancelado'
                else:
                    order.sof_cobro_estado = 'pagado'
            else:
                order.sof_cobro_estado = 'na'

            # ── DESPACHO: estado físico de la entrega ─────────────────────────
            outgoing = order.picking_ids.filtered(
                lambda p: p.picking_type_code == 'outgoing'
            )
            all_cancelled = (
                outgoing
                and all(p.state == 'cancel' for p in outgoing)
            )

            if is_cancelled or all_cancelled:
                order.sof_entrega_estado = 'cancelado'
            elif op == 'quotation':
                order.sof_entrega_estado = 'na'
            elif op == 'confirmed':
                order.sof_entrega_estado = 'pendiente'
            elif op == 'prepared':
                order.sof_entrega_estado = 'preparado'
            elif op == 'paid':
                # Detectar despacho parcial: algún picking done y otro pendiente
                done_picks = outgoing.filtered(lambda p: p.state == 'done')
                order.sof_entrega_estado = 'parcial' if done_picks else 'listo'
            elif op == 'in_delivery':
                order.sof_entrega_estado = 'en_reparto'
            elif op == 'dispatched':
                order.sof_entrega_estado = 'entregado'
            else:
                order.sof_entrega_estado = 'na'

    @api.depends('is_sof_order')
    def _compute_sof_show_buttons(self):
        """Controla la visibilidad de los smart buttons de factura y entrega.

        Para pedidos SOF aplica las mismas restricciones por rol que el flujo operativo.
        Para pedidos nativos ambos botones son visibles (el ACL nativo de Odoo controla el acceso).
        """
        is_supervisor = self.env.user.has_group('sale_op_flow.group_sale_supervisor')
        for order in self:
            if not order.is_sof_order:
                order.sof_show_invoice_button = True
                order.sof_show_delivery_button = True
            else:
                order.sof_show_invoice_button = is_supervisor
                order.sof_show_delivery_button = is_supervisor

    @api.depends('validity_date', 'operational_state', 'is_sof_order')
    def _compute_sof_validity_status(self):
        today = fields.Date.today()
        try:
            warning_days = int(self.env['ir.config_parameter'].sudo().get_param(
                'sale_op_flow.expiry_warning_days', '3') or 3)
        except (ValueError, TypeError):
            warning_days = 3
        warning_limit = today + timedelta(days=warning_days)
        for order in self:
            if not order.is_sof_order or order.operational_state != 'quotation':
                order.sof_validity_status = False
                continue
            if not order.validity_date:
                order.sof_validity_status = 'valid'
                continue
            if order.validity_date < today:
                order.sof_validity_status = 'expired'
            elif order.validity_date <= warning_limit:
                order.sof_validity_status = 'expiring'
            else:
                order.sof_validity_status = 'valid'

    @api.depends('order_line.product_id', 'order_line.product_id.type')
    def _compute_is_service_order(self):
        for order in self:
            lines = order.order_line.filtered(lambda l: l.product_id and not l.display_type)
            is_service = bool(lines) and all(l.product_id.type == 'service' for l in lines)
            order.is_service_order = is_service
            order.sof_service_label = 'Servicio' if is_service else False

    def action_confirm(self):
        """
        Al confirmar:
        1. Llama al confirm estándar de Odoo (genera picking)
        2. operational_state → confirmed (aparece en cola del cajero y en despacho)
        3. NO crea factura — el cajero la crea al cobrar eligiendo el diario
        """
        today = fields.Date.today()
        for order in self:
            if order.is_sof_order and order.validity_date and order.validity_date < today:
                raise UserError(
                    _('El presupuesto "%s" venció el %s. '
                      'Usá el botón "Renovar vigencia" antes de confirmar.')
                    % (order.name, order.validity_date.strftime('%d/%m/%Y'))
                )

        # Evitar que el override de write sincronice antes de que este método
        # cargue confirmed_by, confirmed_date y el mensaje operativo.
        res = super(SaleOrder, self.with_context(sof_skip_operational_sync=True)).action_confirm()
        for order in self:
            if order.is_sof_order and order.operational_state == 'quotation':
                order.write({
                    'operational_state': 'confirmed',
                    'confirmed_by': self.env.uid,
                    'confirmed_date': fields.Datetime.now(),
                })
                order.message_post(
                    body=_('Pedido confirmado por <b>%s</b>. '
                           'Disponible en cola de caja y en preparación de despacho.')
                    % self.env.user.name
                )
        return res

    # ── Wizard de cobro ────────────────────────────────────────────────────

    def action_open_cashier_payment_wizard(self):
        self.ensure_one()
        if self.operational_state not in ('confirmed', 'prepared'):
            raise UserError(
                _('Este pedido no está disponible para cobro. Estado actual: %s')
                % dict(OPERATIONAL_STATES).get(self.operational_state, self.operational_state)
            )
        # Construir contexto de creación (incluye sesión de caja si viene de tarjeta)
        create_ctx = {
            'default_sale_order_id': self.id,
            'default_company_id': self.company_id.id,
        }
        if self.env.context.get('sof_cashier_session_id'):
            create_ctx['sof_cashier_session_id'] = self.env.context['sof_cashier_session_id']
            create_ctx['default_cashier_session_id'] = self.env.context['sof_cashier_session_id']

        # Crear wizard server-side para que los computed fields (totales, has_payment_line)
        # funcionen correctamente desde la primera apertura del formulario.
        wizard = self.env['sale.cashier.payment.wizard'].with_context(create_ctx)._create_for_order(self)

        # Preservar solo el contexto de sesión al abrir el form (default_* ya no se necesitan)
        open_ctx = {k: v for k, v in create_ctx.items() if not k.startswith('default_')}
        return {
            'name': _('Registrar cobro — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'sale.cashier.payment.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': open_ctx,
        }

    # ── Cancelar / Reabrir ─────────────────────────────────────────────────

    def action_op_cancel(self):
        self.ensure_one()
        if not self.is_sof_order:
            raise UserError(_('Esta acción solo está disponible para pedidos del flujo operativo SOF.'))
        if self.operational_state in ('paid', 'in_delivery', 'dispatched'):
            if not self.env.user.has_group('sale_op_flow.group_sale_supervisor'):
                raise AccessError(_('Solo un supervisor puede cancelar pedidos ya cobrados o despachados.'))
        if self.state not in ('cancel', 'draft'):
            self.action_cancel()
        self.operational_state = 'cancelled'
        self.message_post(body=_('Cancelado por <b>%s</b>.') % self.env.user.name)

    def action_op_reopen(self):
        self.ensure_one()
        if not self.is_sof_order:
            raise UserError(_('Esta acción solo está disponible para pedidos del flujo operativo SOF.'))
        if not self.env.user.has_group('sale_op_flow.group_sale_supervisor'):
            raise AccessError(_('Solo un supervisor puede reabrir pedidos.'))
        if self.operational_state != 'cancelled':
            raise UserError(_('Solo se pueden reabrir pedidos cancelados.'))
        self.action_draft()
        self.write({
            'operational_state': 'quotation',
            'dispatch_prepared': False,
            'dispatch_prepared_by': False,
            'dispatch_prepared_date': False,
        })
        self.message_post(body=_('Reabierto por supervisor <b>%s</b>.') % self.env.user.name)

    def action_view_cashier_session(self):
        self.ensure_one()
        if not self.cashier_session_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.cashier.session',
            'res_id': self.cashier_session_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ── Despacho operativo desde la venta ──────────────────────────────────

    def _sof_outgoing_pickings(self):
        """Entregas de salida reales vinculadas al pedido."""
        return self.picking_ids.filtered(
            lambda picking: picking.picking_type_code == 'outgoing'
            and picking.state != 'cancel'
        )

    def _sof_invalidate_pickings_cache(self):
        """Compatibilidad entre versiones para refrescar la relación de entregas."""
        try:
            self.invalidate_recordset(['picking_ids'])
        except AttributeError:
            self.invalidate_cache(['picking_ids'])

    def _sof_allow_dispatch_without_stock(self):
        """Configuración global del módulo para permitir validar entregas sin reserva.

        Por decisión funcional, el valor por defecto es activo para no frenar ventas
        mientras se ordena el stock. Desde Ajustes del flujo puede desactivarse.
        """
        value = self.env['ir.config_parameter'].sudo().get_param(
            'sale_op_flow.allow_dispatch_without_stock',
            '1',
        )
        return str(value).lower() in ('1', 'true', 't', 'yes', 'y', 'on', 'si', 'sí')

    def _sof_force_dispatch_without_stock(self, pickings):
        """Carga cantidad hecha = demanda para permitir despacho sin stock reservado.

        Usa la mecánica estándar de Odoo (`stock.move._set_quantity_done`) para
        que el movimiento real siga pasando por Inventario. No se fuerza
        automáticamente en productos con lote/serie porque Odoo necesita esos datos.
        """
        self.ensure_one()
        tracked_moves = pickings.move_ids.filtered(
            lambda move: move.state not in ('done', 'cancel')
            and move.product_id.tracking != 'none'
        )
        if tracked_moves:
            products = ', '.join(tracked_moves.mapped('product_id.display_name'))
            raise UserError(
                _('No se puede forzar despacho sin stock para productos con lote/serie.\n\n'
                  'Completá los lotes/series desde la entrega antes de validar.\n'
                  'Productos: %s') % products
            )

        for picking in pickings.filtered(lambda p: p.state not in ('done', 'cancel')):
            if picking.state == 'draft':
                picking.sudo().action_confirm()
            moves = picking.move_ids.filtered(lambda move: move.state not in ('done', 'cancel'))
            for move in moves:
                qty = move.product_uom_qty
                if move.product_uom.compare(qty, 0.0) <= 0:
                    continue
                move.sudo()._set_quantity_done(qty)
                # En Odoo 19 la validación real toma solo líneas/movimientos marcados como picked.
                move.sudo().write({'picked': True})
                move.move_line_ids.sudo().write({'picked': True})

        pickings.invalidate_recordset(['state', 'move_ids', 'move_line_ids'])
        return True

    def _sof_get_or_launch_delivery_pickings(self):
        """Obtiene las entregas del pedido o intenta generarlas con la regla estándar.

        No duplica la lógica de stock: si el pedido no tiene picking, vuelve a lanzar
        la regla estándar de `sale_stock` para líneas entregables. Si aun así no se
        genera una entrega, se informa el motivo al usuario de despacho.
        """
        self.ensure_one()
        pickings = self._sof_outgoing_pickings()
        if pickings:
            return pickings

        # Productos que pueden necesitar entrega:
        # - Odoo 19: 'consu' (consumable/storable) o 'product' (storable legacy)
        # - Excluir solo 'service' (los servicios no generan pickings)
        deliverable_lines = self.order_line.filtered(
            lambda line: not line.display_type
            and not getattr(line, 'is_downpayment', False)
            and line.product_id.type != 'service'
        )
        if not deliverable_lines:
            # Sin líneas entregables: todos los productos son servicios.
            # Marcar como despachado directamente (no requiere picking físico).
            self._mark_as_dispatched()
            return self.env['stock.picking']  # Recordset vacío

        # Defensa para pedidos confirmados antes de que se generara el picking.
        deliverable_lines.sudo()._action_launch_stock_rule()
        self._sof_invalidate_pickings_cache()
        pickings = self._sof_outgoing_pickings()
        if not pickings:
            raise UserError(
                _('El pedido "%s" está confirmado/pagado, pero no tiene una orden de entrega generada.\n\n'
                  'Revisá el almacén, las rutas, el tipo de producto o las reglas de abastecimiento.')
                % self.name
            )
        return pickings

    def action_view_delivery_orders_sof(self):
        """Abre las entregas relacionadas sin obligar al usuario a navegar por Inventario."""
        self.ensure_one()
        pickings = self._sof_outgoing_pickings()
        if not pickings:
            raise UserError(
                _('El pedido "%s" todavía no tiene una orden de entrega generada.')
                % self.name
            )
        action = self.env.ref('stock.action_picking_tree_all').sudo().read()[0]
        action.update({
            'name': _('Entregas — %s') % self.name,
            'domain': [('id', 'in', pickings.ids)],
            'context': dict(self.env.context, create=False),
        })
        if len(pickings) == 1:
            action.update({
                'views': [(False, 'form')],
                'res_id': pickings.id,
            })
        return action

    def action_print_sof_quotation(self):
        """Imprime el presupuesto (para cajero y vendedor en estado quotation)."""
        self.ensure_one()
        return self.env.ref('sale.action_report_saleorder').report_action(self)

    def action_sof_renew_validity(self):
        """Renueva la vigencia del presupuesto X días desde hoy según configuración."""
        self.ensure_one()
        try:
            days = int(self.env['ir.config_parameter'].sudo().get_param(
                'sale_op_flow.quotation_validity_days', '15') or 15)
        except (ValueError, TypeError):
            days = 15
        if days <= 0:
            days = 15
        new_date = fields.Date.today() + timedelta(days=days)
        self.validity_date = new_date
        self.message_post(
            body=_('Vigencia renovada por <b>%s</b>. Nueva fecha: %s.')
            % (self.env.user.name, new_date.strftime('%d/%m/%Y'))
        )

    def action_print_invoice_sof(self):
        """Imprime la factura del pedido (para el botón en la vista del pedido pagado)."""
        self.ensure_one()
        invoice = self.invoice_ids.filtered(
            lambda i: i.state == 'posted' and i.move_type == 'out_invoice'
        )[:1]
        if not invoice:
            raise UserError(_('No hay factura generada para este pedido.'))
        return self.env.ref('account.account_invoices').report_action(invoice)

    def action_print_remito_sof(self):
        """Imprime el remito/albarán de entrega del pedido."""
        self.ensure_one()
        picking = self._sof_outgoing_pickings().filtered(
            lambda p: p.state == 'done'
        )[:1]
        if not picking:
            picking = self._sof_outgoing_pickings()[:1]
        if not picking:
            raise UserError(_('No hay entrega asociada a este pedido.'))
        return self.env.ref('stock.action_report_delivery').report_action(picking)

    def action_sof_unlock(self):
        """Desbloquea el pedido para editar líneas. Cancela el picking pendiente para que se recree."""
        self.ensure_one()
        if self.operational_state in ('paid', 'in_delivery', 'dispatched'):
            raise UserError(_('No se puede desbloquear un pedido ya pagado o despachado. '
                              'Usá Cambio / Devolución para modificar artículos.'))
        pending_pickings = self.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel'))
        if pending_pickings:
            pending_pickings.action_cancel()
        self.action_unlock()

    def action_sof_relock(self):
        """Vuelve a bloquear el pedido y recrea el picking con las líneas actualizadas."""
        self.ensure_one()
        if self.operational_state in ('paid', 'in_delivery', 'dispatched'):
            raise UserError(_('El pedido ya fue procesado y no puede volver a bloquearse desde aquí.'))
        self.action_lock()
        self.order_line._action_launch_stock_rule()

    def _sof_cashier_needs_pin(self):
        """True si el usuario actual (cajero, no supervisor) debe pasar el PIN de
        supervisor antes de NC / Cambio, según el check de Ajustes."""
        self.ensure_one()
        if self.env.context.get('sof_supervisor_authorized'):
            return False
        if self.env.user.has_group('sale_op_flow.group_sale_supervisor'):
            return False
        return self._sof_str_to_bool(self.env['ir.config_parameter'].sudo().get_param(
            'sale_op_flow.cashier_actions_require_pin', '0'))

    def _sof_open_supervisor_pin_wizard(self, action_type):
        self.ensure_one()
        wiz = self.env['sof.supervisor.pin.wizard'].create({
            'order_id': self.id,
            'action_type': action_type,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Autorización de supervisor'),
            'res_model': 'sof.supervisor.pin.wizard',
            'res_id': wiz.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_exchange_wizard(self):
        self.ensure_one()
        if self._sof_cashier_needs_pin():
            return self._sof_open_supervisor_pin_wizard('exchange')
        if self.operational_state not in ('paid', 'in_delivery', 'dispatched'):
            raise UserError(_('Solo se puede registrar un cambio en pedidos pagados o entregados.'))
        if not self.invoice_ids.filtered(lambda i: i.move_type == 'out_invoice' and i.state == 'posted'):
            raise UserError(_('Se requiere una factura confirmada para poder hacer el cambio.'))
        if self.sof_fully_returned:
            raise UserError(_('Este pedido ya fue devuelto totalmente. '
                              'No se pueden registrar más devoluciones.'))
        wizard = self.env['sale.exchange.wizard']._create_for_order(self)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cambio / Devolución'),
            'res_model': 'sale.exchange.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_view_exchanges(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cambios / Devoluciones'),
            'res_model': 'sale.exchange',
            'view_mode': 'list,form',
            'domain': [('order_id', '=', self.id)],
        }

    def action_prepare_dispatch(self):
        """Prepara/reserva la entrega desde el menú Despacho.

        El usuario no entra al módulo Inventario: el botón confirma el picking si
        está en borrador y ejecuta la reserva estándar (`action_assign`).
        """
        notification_type = 'success'
        messages = []
        for order in self:
            if order.operational_state not in ('confirmed', 'prepared', 'paid'):
                raise UserError(
                    _('El pedido "%s" no está disponible para preparar despacho. Estado actual: %s')
                    % (order.name, dict(OPERATIONAL_STATES).get(order.operational_state, order.operational_state))
                )

            pickings = order._sof_get_or_launch_delivery_pickings()
            if not pickings:
                # Productos sin entrega física (servicios): marcar como preparado directamente
                new_state = 'prepared' if order.operational_state == 'confirmed' else order.operational_state
                order.write({
                    'dispatch_prepared': True,
                    'dispatch_prepared_by': self.env.uid,
                    'dispatch_prepared_date': fields.Datetime.now(),
                    'operational_state': new_state,
                })
                messages.append(_('%s: sin entrega física (servicios), preparado.') % order.name)
                continue
            pending = pickings.filtered(lambda picking: picking.state not in ('done', 'cancel'))
            if not pending:
                new_state = 'prepared' if order.operational_state == 'confirmed' else order.operational_state
                order.write({
                    'dispatch_prepared': True,
                    'dispatch_prepared_by': self.env.uid,
                    'dispatch_prepared_date': fields.Datetime.now(),
                    'operational_state': new_state,
                })
                messages.append(_('%s ya tenía la entrega procesada.') % order.name)
                continue

            draft = pending.filtered(lambda picking: picking.state == 'draft')
            if draft:
                draft.sudo().action_confirm()

            to_assign = pending.filtered(lambda picking: picking.state in ('waiting', 'confirmed'))
            if to_assign:
                to_assign.sudo().action_assign()

            pending.invalidate_recordset(['state'])
            ready = pending.filtered(lambda picking: picking.state == 'assigned')
            if ready:
                new_state = 'prepared' if order.operational_state == 'confirmed' else order.operational_state
                order.write({
                    'dispatch_prepared': True,
                    'dispatch_prepared_by': self.env.uid,
                    'dispatch_prepared_date': fields.Datetime.now(),
                    'operational_state': new_state,
                })
                order.message_post(
                    body=_('📦 Despacho preparado por <b>%s</b>. Entrega reservada/lista para validar.')
                    % self.env.user.name
                )
                messages.append(_('%s: despacho preparado.') % order.name)
            else:
                if order._sof_allow_dispatch_without_stock():
                    new_state = 'prepared' if order.operational_state == 'confirmed' else order.operational_state
                    order.write({
                        'dispatch_prepared': True,
                        'dispatch_prepared_by': self.env.uid,
                        'dispatch_prepared_date': fields.Datetime.now(),
                        'operational_state': new_state,
                    })
                    notification_type = 'warning'
                    order.message_post(
                        body=_('⚠️ Despacho preparado por <b>%s</b> sin stock reservado. '
                               'La configuración permite confirmar despacho sin stock y podría generarse stock negativo.')
                        % self.env.user.name
                    )
                    messages.append(_('%s: preparado sin stock reservado por configuración.') % order.name)
                else:
                    notification_type = 'warning'
                    order.message_post(
                        body=_('⚠️ <b>%s</b> intentó preparar el despacho, pero la entrega no quedó disponible. '
                               'Revisá stock/disponibilidad.') % self.env.user.name
                    )
                    messages.append(_('%s: no quedó disponible por falta de stock o reglas de abastecimiento.') % order.name)

        next_action = {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self[0].id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        } if len(self) == 1 else {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Preparar despacho'),
                'message': '\n'.join(messages),
                'type': notification_type,
                'sticky': notification_type == 'warning',
                'next': next_action,
            },
        }

    def action_confirm_dispatch(self):
        """Abre el wizard de despacho para controlar cantidades parciales.

        El wizard se crea server-side antes de abrir el formulario para que
        move_id (required) quede persistido y no dependa del payload del cliente.
        """
        self.ensure_one()
        if self.operational_state != 'paid':
            raise UserError(
                _('Solo se puede confirmar despacho cuando el pedido está Pagado. Estado actual: %s')
                % dict(OPERATIONAL_STATES).get(self.operational_state, self.operational_state)
            )
        wizard = self.env['sale.dispatch.wizard']._create_for_order(self)
        return {
            'name': _('Confirmar despacho — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'sale.dispatch.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm_delivery(self):
        """Confirma la recepción del cliente cuando el pedido está en reparto."""
        self.ensure_one()
        if self.operational_state != 'in_delivery':
            raise UserError(
                _('Solo se puede confirmar entrega cuando el pedido está En reparto.')
            )
        self._mark_as_dispatched()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Entrega confirmada'),
                'message': _('El pedido %s fue entregado al cliente.') % self.name,
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'sale.order',
                    'res_id': self.id,
                    'view_mode': 'form',
                    'views': [(False, 'form')],
                    'target': 'current',
                },
            },
        }

    # ── Lógica de cobro (llamada desde el wizard) ──────────────────────────

    def _complete_payment(self, payment_journal, financing_plan, cashier_session,
                           coupon_number=False, invoice_journal=None):
        """
        Cobro completo en caja:
        1. Crea la factura con el diario elegido por el cajero
        2. Aplica ajuste (descuento/recargo)
        3. Valida la factura
        4. Registra y reconcilia el pago
        5. operational_state → paid (despacho puede entregar)

        Args:
            payment_journal:  account.journal — diario del cobro (efectivo, banco, etc.)
            financing_plan:   sale.financing.plan — plan de cuotas/ajuste
            cashier_session:  sale.cashier.session — sesión activa del cajero
            coupon_number:    str — número de cupón/voucher (opcional)
            invoice_journal:  account.journal — diario de facturación (elegido por cajero)
        """
        self.ensure_one()
        if self.operational_state not in ('confirmed', 'prepared'):
            raise UserError(
                _('El pedido "%s" no está disponible para cobro (estado: %s).')
                % (self.name, dict(OPERATIONAL_STATES).get(self.operational_state, self.operational_state))
            )

        # El diario real del cobro debe salir del plan cuando el cajero eligió
        # un plan de pago. Es una segunda defensa por si este método se llama
        # desde otro lugar distinto al wizard.
        effective_payment_journal = payment_journal
        if financing_plan and financing_plan.payment_journal_id:
            effective_payment_journal = financing_plan.payment_journal_id
        if not effective_payment_journal:
            raise UserError(_('Seleccioná un diario/medio de cobro.'))

        self.write({
            'final_payment_journal_id': effective_payment_journal.id,
            'financing_plan_id': financing_plan.id if financing_plan else False,
        })

        invoice = self._get_or_create_draft_invoice(journal=invoice_journal)
        if not invoice:
            raise UserError(
                _('No se pudo crear la factura para "%s". '
                  'Verificá que los productos tienen política de facturación "Pedido".') % self.name
            )

        self._apply_adjustment_to_invoice(plan=financing_plan, invoice=invoice)
        invoice.write({'invoice_date': fields.Date.today()})
        invoice.action_post()

        payment = self._register_payment_on_invoice(
            invoice=invoice,
            journal=effective_payment_journal,
            financing_plan=financing_plan,
            cashier_session=cashier_session,
            coupon_number=coupon_number,
        )

        self.write({
            'operational_state': 'paid',
            'cashier_session_id': cashier_session.id if cashier_session else False,
            'collected_by': self.env.uid,
            'collected_date': fields.Datetime.now(),
        })
        if self.is_service_order:
            self._mark_as_dispatched()

        plan_name = financing_plan.name if financing_plan else payment_journal.name
        self.message_post(
            body=_('💰 Cobrado por <b>%s</b>. Medio: %s | Total: %s %.2f<br/>'
                   '✅ Listo para despacho.')
            % (self.env.user.name, plan_name, self.currency_id.symbol, invoice.amount_total)
        )
        return payment

    def _complete_multi_payment(self, payment_lines, cashier_session,
                                invoice_journal=None, payment_mode='single'):
        """
        Cobro en caja (pago único o multi-método):

        Modo 'single':
          - Ajuste (descuento/recargo) calculado sobre la base imponible del pedido
            usando _apply_adjustment_to_invoice (comportamiento original).
          - invoice_total = order_total ± plan_adjustment_on_untaxed

        Modo 'multi':
          - Cada línea puede tener recargo (NO descuento) aplicado sobre el monto
            de esa línea. El usuario ingresa el monto final ya con el recargo.
          - Ajuste en factura = sum(líneas) - order_total (diferencia total).
          - Se crea un account.payment por cada línea.
          - Todos los cobros se reconcilian contra la factura.

        Args:
            payment_lines:  recordset de sale.cashier.payment.line
            cashier_session: sale.cashier.session
            invoice_journal: account.journal — diario de facturación
            payment_mode:   'single' | 'multi'
        """
        self.ensure_one()
        if self.operational_state not in ('confirmed', 'prepared'):
            raise UserError(
                _('El pedido "%s" no está disponible para cobro (estado: %s).')
                % (self.name, dict(OPERATIONAL_STATES).get(self.operational_state, self.operational_state))
            )

        invoice = self._get_or_create_draft_invoice(journal=invoice_journal)
        if not invoice:
            raise UserError(
                _('No se pudo crear la factura para "%s". '
                  'Verificá que los productos tienen política de facturación "Pedido".') % self.name
            )

        if payment_mode == 'single':
            # Ajuste sobre base imponible del pedido (comportamiento original)
            adjustment_plan = next(
                (l.financing_plan_id for l in payment_lines
                 if l.financing_plan_id
                 and l.financing_plan_id.adjustment_type != 'none'
                 and l.financing_plan_id.adjustment_rate),
                None
            )
            self._apply_adjustment_to_invoice(plan=adjustment_plan, invoice=invoice)
        else:
            # Solo agregar a la factura los recargos de planes de financiamiento.
            # El exceso de cheques (cheque mayor al adeudado) NO se incluye: queda
            # como crédito a favor del cliente vía reconciliación parcial natural.
            surcharge_total = 0.0
            for line in payment_lines:
                plan = line.financing_plan_id
                if plan and plan.adjustment_type == 'surcharge' and plan.adjustment_rate and (line.amount or 0.0) > 0:
                    base = round(line.amount / (1.0 + plan.adjustment_rate / 100.0), 2)
                    surcharge_total += line.amount - base
            if abs(surcharge_total) > 0.01:
                adj_plan = next(
                    (l.financing_plan_id for l in payment_lines
                     if l.financing_plan_id and l.financing_plan_id.adjustment_product_id),
                    None
                )
                self._apply_fixed_adjustment_to_invoice(invoice, round(surcharge_total, 2), plan=adj_plan)

        pay_later_lines = payment_lines.filtered(lambda l: l.line_type == 'cc')
        # Aplicar término de pago de la línea CC a la factura ANTES de publicarla
        if pay_later_lines:
            pay_later_plan = pay_later_lines[:1].financing_plan_id
            if pay_later_plan and pay_later_plan.payment_term_id:
                invoice.write({'invoice_payment_term_id': pay_later_plan.payment_term_id.id})

        invoice.write({'invoice_date': fields.Date.today()})
        invoice.action_post()

        Payment = self.env['account.payment']
        payments = Payment
        payment_memo = '%s - %s' % (self.name, invoice.name or '')

        for line in payment_lines:
            if line.line_type == 'cc':
                continue  # CC: no se crea pago inmediato; la factura queda pendiente

            effective_journal = line.payment_journal_id
            if line.financing_plan_id and line.financing_plan_id.payment_journal_id:
                effective_journal = line.financing_plan_id.payment_journal_id

            is_check = line.line_type == 'check'

            payment_vals = {
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': invoice.partner_id.commercial_partner_id.id,
                'amount': line.amount,
                'journal_id': effective_journal.id,
                'date': fields.Date.today(),
                'currency_id': invoice.currency_id.id,
                'company_id': self.company_id.id,
                'op_sale_order_id': self.id,
                'op_cashier_session_id': cashier_session.id if cashier_session else False,
                'op_financing_plan_id': line.financing_plan_id.id if line.financing_plan_id else False,
                'op_coupon_number': line.coupon_number or False,
            }

            if is_check:
                # Buscar el método de pago "Cheques de terceros recibidos" en el diario
                pml = effective_journal.inbound_payment_method_line_ids.filtered(
                    lambda m: m.code == 'new_third_party_checks'
                )[:1]
                if not pml:
                    raise UserError(_(
                        'El diario "%s" no tiene configurado el método '
                        '"Cheques de terceros recibidos".\n'
                        'Activalo desde Contabilidad → Diarios → %s → Pagos entrantes.'
                    ) % (effective_journal.name, effective_journal.name))
                payment_vals['payment_method_line_id'] = pml.id
                # Cheque inline con el pago para que _compute_amount lo vea al momento
                # de la creación y el monto del payment coincida con el del cheque.
                check_number = (line.check_number or '').strip()
                if check_number:
                    check_number = check_number.zfill(8)
                payment_vals['l10n_latam_new_check_ids'] = [Command.create({
                    'name': check_number or False,
                    'bank_id': line.check_bank_id.id if line.check_bank_id else False,
                    'issuer_vat': line.check_issuer_vat or False,
                    'payment_date': line.check_payment_date or fields.Date.today(),
                    'amount': line.amount,
                })]

            if 'memo' in Payment._fields:
                payment_vals['memo'] = payment_memo
            elif 'ref' in Payment._fields:
                payment_vals['ref'] = payment_memo

            payment = Payment.create(payment_vals)

            payment.action_post()
            payments |= payment

        self._reconcile_payments_to_invoice(invoice, payments)

        first_line = payment_lines[:1]
        self.write({
            'final_payment_journal_id': first_line.payment_journal_id.id if first_line else False,
            'financing_plan_id': (
                first_line.financing_plan_id.id
                if first_line and first_line.financing_plan_id else False
            ),
            'operational_state': 'paid',
            'cashier_session_id': cashier_session.id if cashier_session else False,
            'collected_by': self.env.uid,
            'collected_date': fields.Datetime.now(),
            'is_credit_sale': bool(pay_later_lines),
        })
        if self.is_service_order:
            self._mark_as_dispatched()

        non_cc_lines = payment_lines.filtered(lambda l: l.line_type != 'cc')
        journal_names = ', '.join(dict.fromkeys(
            l.payment_journal_id.name for l in non_cc_lines if l.payment_journal_id
        )) or '—'
        cc_amount = sum(l.amount for l in pay_later_lines)
        paid_amount = sum(l.amount for l in non_cc_lines)

        if pay_later_lines:
            cc_plan = pay_later_lines[:1].financing_plan_id
            term_name = cc_plan.payment_term_id.name if cc_plan.payment_term_id else _('sin plazo definido')
            cc_note = _(
                '<br/>💳 Cuenta Corriente: %s %.2f (%s). Factura queda pendiente de cobro.'
            ) % (self.currency_id.symbol, cc_amount, term_name)
        else:
            cc_note = ''

        self.message_post(
            body=_('Cobrado por <b>%s</b>. Medios: %s | Efectivo/Trans: %s %.2f%s<br/>Listo para despacho.')
            % (self.env.user.name, journal_names, self.currency_id.symbol, paid_amount, cc_note)
        )
        return payments

    def _apply_fixed_adjustment_to_invoice(self, invoice, amount, plan=None):
        """Agrega una línea de ajuste de monto fijo a la factura.

        Usado en cobros multi-método donde el recargo es la diferencia entre
        lo cobrado (líneas con recargo incluido) y el total original del pedido.

        Args:
            invoice: account.move en estado draft
            amount:  monto en moneda de la factura (positivo = recargo, negativo = descuento)
            plan:    sale.financing.plan con adjustment_product_id (para la cuenta contable)
        """
        self.ensure_one()
        if invoice.state != 'draft':
            raise UserError(_('La factura ya fue validada.'))
        old_adj = invoice.invoice_line_ids.filtered(lambda l: l.is_sof_adjustment_line)
        if old_adj:
            old_adj.unlink()
        if abs(amount) <= 0.01:
            return
        product = plan.adjustment_product_id if plan else None
        if not product:
            raise UserError(_(
                'Para cobros con recargo en múltiples pagos, el plan de pago debe '
                'tener un producto de ajuste configurado (Configuración → Planes de pago).'
            ))
        account = (
            product.property_account_income_id
            or product.categ_id.property_account_income_categ_id
            or invoice.journal_id.default_account_id
        )
        if not account:
            raise UserError(_('Sin cuenta contable para el producto de ajuste "%s".') % product.name)
        label = _('Recargo por medio de pago') if amount > 0 else _('Descuento por medio de pago')
        invoice.write({'invoice_line_ids': [(0, 0, {
            'product_id': product.id,
            'name': label,
            'quantity': 1.0,
            'price_unit': amount,
            'account_id': account.id,
            'tax_ids': [(5, 0, 0)],
            'is_sof_adjustment_line': True,
        })]})

    def _get_configured_cash_rounding(self):
        try:
            rid = int(self.env['ir.config_parameter'].sudo().get_param(
                'sale_op_flow.cash_rounding_id', '0') or 0)
        except (ValueError, TypeError):
            return self.env['account.cash.rounding']
        return self.env['account.cash.rounding'].browse(rid).exists() and \
               self.env['account.cash.rounding'].browse(rid) or \
               self.env['account.cash.rounding']

    def _create_operational_invoice(self, journal=None):
        """Crea la factura borrador con el diario elegido por el cajero."""
        self.ensure_one()
        existing = self.invoice_ids.filtered(lambda inv: inv.move_type == 'out_invoice')
        if existing:
            draft = existing.filtered(lambda inv: inv.state == 'draft')
            return draft[:1] or existing[:1]
        ctx = {}
        if journal:
            ctx['default_journal_id'] = journal.id
        invoices = self.with_context(**ctx)._create_invoices()
        invoices.write({'invoice_date': False})
        # Aplicar posición fiscal del diario si está configurada (ej. Auto LB → FP sin IVA).
        # Usamos _compute_tax_ids en lugar de action_update_fpos_values para recomputar
        # solo los impuestos sin alterar el price_unit (action_update_fpos_values divide el
        # precio por el coeficiente del IVA cuando éste es price_include, lo que reduce el
        # total de la factura en lugar de mantenerlo igual sin IVA).
        fp = journal and getattr(journal, 'prs_fiscal_position_id', False)
        rounding = self._get_configured_cash_rounding()
        for inv in invoices.filtered(lambda i: i.state == 'draft'):
            updates = {}
            if fp and inv.fiscal_position_id != fp:
                updates['fiscal_position_id'] = fp.id
            if rounding and inv.invoice_cash_rounding_id != rounding:
                updates['invoice_cash_rounding_id'] = rounding.id
            if updates:
                inv.write(updates)
                if 'fiscal_position_id' in updates:
                    inv.invoice_line_ids._compute_tax_ids()
        return invoices[:1]

    def _get_or_create_draft_invoice(self, journal=None):
        """Crea la factura borrador con el diario elegido por el cajero."""
        self.ensure_one()
        existing = self.invoice_ids.filtered(
            lambda inv: inv.move_type == 'out_invoice' and inv.state == 'draft'
        )
        if existing:
            inv = existing[:1]
            updates = {}
            if journal and inv.journal_id != journal:
                updates['journal_id'] = journal.id
            fp = journal and getattr(journal, 'prs_fiscal_position_id', False)
            if fp and inv.fiscal_position_id != fp:
                updates['fiscal_position_id'] = fp.id
            rounding = self._get_configured_cash_rounding()
            if rounding and inv.invoice_cash_rounding_id != rounding:
                updates['invoice_cash_rounding_id'] = rounding.id
            if updates:
                inv.write(updates)
                if 'fiscal_position_id' in updates:
                    inv.invoice_line_ids._compute_tax_ids()
            return inv
        return self._create_operational_invoice(journal=journal)

    def _reconcile_payments_to_invoice(self, invoice, payments):
        """Reconcilia cada pago individualmente contra la factura en orden de creación.

        Al reconciliar de a uno, todos los pagos quedan vinculados a la factura en el
        widget "Pagos", incluso cuando el total pagado supera el importe de la factura.
        El exceso del último pago queda como crédito a favor del cliente.
        """
        invoice_ar = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )
        for payment in payments:
            inv_line = invoice_ar.filtered(lambda l: not l.reconciled)
            if not inv_line:
                break  # Factura saldada en su totalidad
            pmt_line = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
            )
            if pmt_line:
                (inv_line[:1] + pmt_line[:1]).reconcile()

    def _apply_adjustment_to_invoice(self, plan, invoice):
        self.ensure_one()
        if invoice.state != 'draft':
            raise UserError(_('La factura ya fue validada.'))
        old_adj = invoice.invoice_line_ids.filtered(lambda l: l.is_sof_adjustment_line)
        if old_adj:
            old_adj.unlink()
        if not plan or plan.adjustment_type == 'none' or not plan.adjustment_rate:
            return
        if not plan.adjustment_product_id:
            raise UserError(_('El plan "%s" no tiene producto de ajuste.') % plan.name)

        base = invoice.amount_untaxed
        if plan.adjustment_type == 'discount':
            price_unit = -(base * plan.adjustment_rate / 100.0)
            label = _('Descuento %s (%.2f%%)') % (plan.name, plan.adjustment_rate)
        else:
            price_unit = base * plan.adjustment_rate / 100.0
            label = _('Recargo %s (%.2f%%)') % (plan.name, plan.adjustment_rate)

        product = plan.adjustment_product_id
        account = (
            product.property_account_income_id
            or product.categ_id.property_account_income_categ_id
            or invoice.journal_id.default_account_id
        )
        if not account:
            raise UserError(_('Sin cuenta contable para el producto de ajuste "%s".') % product.name)

        invoice.write({'invoice_line_ids': [(0, 0, {
            'product_id': product.id,
            'name': label,
            'quantity': 1.0,
            'price_unit': price_unit,
            'account_id': account.id,
            'tax_ids': [(5, 0, 0)],
            'is_sof_adjustment_line': True,
        })]})

    def _register_payment_on_invoice(self, invoice, journal, financing_plan=None,
                                      cashier_session=None, coupon_number=False):
        self.ensure_one()
        payment_memo = f'{self.name} - {invoice.name or ""}'
        payment_vals = {
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': invoice.partner_id.commercial_partner_id.id,
            'amount': invoice.amount_total,
            'journal_id': journal.id,
            'date': fields.Date.today(),
            'currency_id': invoice.currency_id.id,
            'company_id': self.company_id.id,
            'op_sale_order_id': self.id,
            'op_cashier_session_id': cashier_session.id if cashier_session else False,
            'op_financing_plan_id': financing_plan.id if financing_plan else False,
            'op_coupon_number': coupon_number or False,
        }
        Payment = self.env['account.payment']
        if 'memo' in Payment._fields:
            # Odoo 19 usa `memo` en account.payment. Luego Odoo propaga ese texto
            # al ref del asiento contable del pago.
            payment_vals['memo'] = payment_memo
        elif 'ref' in Payment._fields:
            # Compatibilidad defensiva si el módulo se instala en una base anterior.
            payment_vals['ref'] = payment_memo

        payment = Payment.create(payment_vals)
        payment.action_post()
        receivable_lines = (payment.move_id.line_ids | invoice.line_ids).filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
        )
        if len(receivable_lines) >= 2:
            receivable_lines.reconcile()
        return payment

    def _mark_as_in_delivery(self, notes=False, delivery_date=False, delivery_shift=False):
        """Marca el pedido como En reparto (salió con flete, pendiente recepción)."""
        for order in self:
            if order.operational_state != 'paid':
                continue
            vals = {
                'operational_state': 'in_delivery',
                'dispatched_by': self.env.uid,
                'dispatched_date': fields.Datetime.now(),
            }
            if notes:
                vals['dispatch_notes'] = notes
            if delivery_date:
                vals['delivery_date'] = delivery_date
            if delivery_shift:
                vals['delivery_shift'] = delivery_shift
            if not order.dispatch_prepared:
                vals.update({
                    'dispatch_prepared': True,
                    'dispatch_prepared_by': self.env.uid,
                    'dispatch_prepared_date': fields.Datetime.now(),
                })
            order.write(vals)
            shift_label = {'morning': 'Mañana', 'afternoon': 'Tarde'}.get(delivery_shift or '', '')
            date_str = delivery_date.strftime('%d/%m/%Y') if delivery_date else ''
            detail = ' — '.join(filter(None, [date_str, shift_label]))
            body = _('🚚 En reparto por <b>%s</b>.') % self.env.user.name
            if detail:
                body += ' %s' % detail
            order.message_post(body=body)

    def _mark_as_dispatched(self):
        for order in self:
            if order.operational_state not in ('paid', 'in_delivery'):
                continue
            vals = {
                'operational_state': 'dispatched',
                'dispatched_by': self.env.uid,
                'dispatched_date': fields.Datetime.now(),
            }
            if not order.dispatch_prepared:
                vals.update({
                    'dispatch_prepared': True,
                    'dispatch_prepared_by': self.env.uid,
                    'dispatch_prepared_date': fields.Datetime.now(),
                })
            order.write(vals)
            order.message_post(
                body=_('📦 Despachado por <b>%s</b>.') % self.env.user.name
            )

    # ── Helper: estado del pago de la factura ─────────────────────────────

    def _is_invoice_paid(self):
        """
        Verifica si la factura del pedido está pagada o en proceso de pago.
        Usado por stock.picking para determinar si puede validar la entrega.
        """
        self.ensure_one()
        invoices = self.invoice_ids.filtered(
            lambda inv: inv.move_type == 'out_invoice' and inv.state == 'posted'
        )
        if not invoices:
            return False
        # payment_state: 'not_paid', 'partial', 'in_payment', 'paid', 'reversed'
        return any(inv.payment_state in ('paid', 'in_payment') for inv in invoices)

    @api.model
    def _cron_cancel_expired_quotations(self):
        """Cancela automáticamente presupuestos SOF vencidos si la opción está activa."""
        param = self.env['ir.config_parameter'].sudo().get_param(
            'sale_op_flow.auto_cancel_expired', '0')
        if str(param).lower() not in ('1', 'true', 't', 'yes', 'y', 'on', 'si', 'sí'):
            return
        today = fields.Date.today()
        expired = self.search([
            ('is_sof_order', '=', True),
            ('operational_state', '=', 'quotation'),
            ('validity_date', '<', today),
            ('state', 'in', ('draft', 'sent')),
        ])
        for order in expired:
            try:
                order.action_op_cancel()
                order.message_post(
                    body=_('Presupuesto cancelado automáticamente por vencimiento '
                           'de vigencia (%s).') % order.validity_date.strftime('%d/%m/%Y')
                )
            except Exception:
                continue
