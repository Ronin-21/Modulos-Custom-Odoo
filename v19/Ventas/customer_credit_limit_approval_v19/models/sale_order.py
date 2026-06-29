# -*- coding: utf-8 -*-
import logging
from odoo import api, models, fields, _
from odoo.exceptions import AccessDenied, ValidationError

_logger = logging.getLogger(__name__)

CREDIT_APPROVER_GROUP = 'customer_credit_limit_approval_v19.group_credit_approver'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    state = fields.Selection(
        selection_add=[
            ('sales_approval', "Aprobación de Crédito"),
            ('approved', "Aprobado"),
            ('reject', "Rechazado"),
        ],
        ondelete={
            'sales_approval': 'set draft',
            'approved': 'set draft',
            'reject': 'set draft',
        }
    )
    amount_due = fields.Monetary(
        related='partner_id.amount_due',
        currency_field='company_currency_id',
        readonly=True
    )
    customer_blocking_limit = fields.Monetary(
        related='partner_id.credit_blocking',
        currency_field='company_currency_id',
        readonly=True
    )
    company_currency_id = fields.Many2one(
        string='Company Currency',
        readonly=True,
        related='company_id.currency_id'
    )
    is_credit_limit_approval = fields.Boolean(
        compute='_compute_customer_credit_limit',
        store=False
    )
    credit_excess = fields.Monetary(
        string='Exceso sobre límite',
        currency_field='company_currency_id',
        compute='_compute_credit_excess',
        store=False,
    )
    is_credit_limit_final_approved = fields.Boolean(
        default=False,
        help='Flag set when Credit Limit is approved'
    )

    # =============== helpers =================
    def _check_salesperson_permission(self):
        """Evita que un vendedor 'B' mande o confirme la orden de un vendedor 'A',
        salvo que sea gerente.
        """
        self.ensure_one()
        # si la orden no tiene vendedor asignado, no controlamos
        if not self.user_id:
            return

        # si el usuario actual ES el vendedor asignado, ok
        if self.user_id == self.env.user:
            return

        # si es gerente de ventas, ERP manager o aprobador de crédito, también ok
        if (
            self.env.user.has_group('sales_team.group_sale_manager')
            or self.env.user.has_group('base.group_erp_manager')
            or self.env.user.has_group(CREDIT_APPROVER_GROUP)
        ):
            return

        # si llegó acá, no tiene permiso
        raise ValidationError(
            _("No puede operar esta cotización porque el vendedor asignado es: %s") % self.user_id.name
        )

    def _safe_post_note(self, body):
        self.ensure_one()
        try:
            self.with_context(
                mail_post_autofollow=False,
                mail_create_nosubscribe=True,
                mail_notify_force_send=False,
                mail_notify_noemail=True,
            ).message_post(
                body=body,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
                partner_ids=[],
            )
        except Exception as e:
            _logger.warning("No se pudo postear nota en SO %s: %s", self.name, e)

    def _create_review_activity_for_managers(self, excess):
        """Crea la actividad en la campanita para los gerentes."""
        self.ensure_one()

        Activity = self.env['mail.activity'].sudo()
        todo_type = self.env.ref('mail.mail_activity_data_todo')

        # id del modelo sale.order
        sale_model_id = self.env['ir.model']._get_id('sale.order')

        approver_group = self.env.ref(CREDIT_APPROVER_GROUP, raise_if_not_found=False)
        user_ids = set()
        if approver_group:
            for user in approver_group.user_ids:
                if user.active:
                    user_ids.add(user.id)

        for uid in user_ids:
            # evitar duplicados
            existing = Activity.search([
                ('res_model_id', '=', sale_model_id),
                ('res_id', '=', self.id),
                ('user_id', '=', uid),
                ('activity_type_id', '=', todo_type.id),
                ('state', '=', 'planned'),
            ], limit=1)
            if existing:
                continue

            Activity.create({
                'res_model_id': sale_model_id,
                'res_id': self.id,
                'activity_type_id': todo_type.id,
                'user_id': uid,
                'summary': _("Revisar aprobación de crédito"),
                'note': _(
                    "La orden %s excede el límite de crédito del cliente %s.\nExceso: $%s.\n"
                    "Aprobá o rechazá desde la orden de venta."
                ) % (self.name, self.partner_id.name, excess),
            })

    def _create_activity_for_salesperson(self, approved, extra_note=None):
        """Crea una actividad para el vendedor avisando si se aprobó o se rechazó."""
        self.ensure_one()
        if not self.user_id:
            return  # la orden no tiene vendedor asignado

        Activity = self.env['mail.activity'].sudo()
        todo_type = self.env.ref('mail.mail_activity_data_todo')
        sale_model_id = self.env['ir.model']._get_id('sale.order')

        # evitar duplicados
        existing = Activity.search([
            ('res_model_id', '=', sale_model_id),
            ('res_id', '=', self.id),
            ('user_id', '=', self.user_id.id),
            ('activity_type_id', '=', todo_type.id),
            ('state', '=', 'planned'),
        ], limit=1)
        if existing:
            return

        if approved:
            summary = _("Orden aprobada y confirmada")
            note = _("La orden %s fue aprobada y confirmada. Ya podés crear la factura y el remito.") % self.name
        else:
            summary = _("Orden rechazada por crédito")
            note = _("La orden %s fue rechazada por crédito. Revisá con gerencia.") % self.name

        if extra_note:
            note = f"{note}\n{extra_note}"

        Activity.create({
            'res_model_id': sale_model_id,
            'res_id': self.id,
            'activity_type_id': todo_type.id,
            'user_id': self.user_id.id,
            'summary': summary,
            'note': note,
        })

    # =============== cómputos =================
    @api.depends(
        'state',
        'amount_due',
        'amount_total',
        'partner_id.credit_check',
        'partner_id.credit_blocking',
        'is_credit_limit_final_approved',
    )
    def _compute_customer_credit_limit(self):
        terminal_states = {'sale', 'done', 'cancel', 'reject'}
        for order in self:
            order.is_credit_limit_approval = False
            if order.state in terminal_states:
                continue
            if not order.partner_id or not order.partner_id.credit_check:
                continue
            total_with_order = (order.amount_due or 0.0) + (order.amount_total or 0.0)
            if (
                total_with_order > (order.customer_blocking_limit or 0.0)
                and not order.is_credit_limit_final_approved
            ):
                order.is_credit_limit_approval = True

    @api.depends('amount_due', 'amount_total', 'customer_blocking_limit', 'partner_id.credit_check')
    def _compute_credit_excess(self):
        for order in self:
            if order.partner_id.credit_check and order.customer_blocking_limit:
                excess = (order.amount_due or 0.0) + (order.amount_total or 0.0) - order.customer_blocking_limit
                order.credit_excess = max(excess, 0.0)
            else:
                order.credit_excess = 0.0

    def _validate_credit_limit(self):
        self.ensure_one()
        if not self.partner_id.credit_check:
            return False
        total_with_order = (self.amount_due or 0.0) + (self.amount_total or 0.0)
        return (
            total_with_order > (self.partner_id.credit_blocking or 0.0)
            and not self.is_credit_limit_final_approved
        )

    # =============== acciones =================
    def action_confirm(self):
        self.ensure_one()
        self._check_salesperson_permission()

        total_with_order = (self.amount_due or 0.0) + (self.amount_total or 0.0)
        if total_with_order <= (self.partner_id.credit_blocking or 0.0):
            # si ya no excede, quitamos la marca de aprobado forzado
            self.is_credit_limit_final_approved = False

        # bloqueo: excede el límite de bloqueo → wizard de aprobación gerencial
        if self._validate_credit_limit():
            difference = round(
                ((self.amount_due or 0.0) + (self.amount_total or 0.0)) - (self.partner_id.credit_blocking or 0.0),
                2,
            )
            return {
                'type': 'ir.actions.act_window',
                'name': 'Límite de Crédito Excedido',
                'res_model': 'credit.approval.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_sale_order_id': self.id,
                    'default_difference': difference,
                }
            }

        # advertencia: excede el monto de advertencia (no el de bloqueo) → aviso no bloqueante
        if not self.env.context.get('credit_warning_acknowledged'):
            warning_limit = self.partner_id.credit_warning or 0.0
            blocking_limit = self.partner_id.credit_blocking or 0.0
            if (
                self.partner_id.credit_check
                and warning_limit
                and total_with_order > warning_limit
                and (not blocking_limit or total_with_order <= blocking_limit)
            ):
                excess_warning = round(total_with_order - warning_limit, 2)
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Advertencia de Crédito',
                    'res_model': 'credit.warning.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_sale_order_id': self.id,
                        'default_excess_warning': excess_warning,
                    }
                }

        ctx = dict(
            self.env.context,
            mail_post_autofollow=False,
            mail_create_nosubscribe=True,
            mail_notify_force_send=False,
            mail_notify_noemail=True,
        )
        return super(SaleOrder, self.with_context(ctx)).action_confirm()

    # =============== notificaciones =================
    def _notify_managers(self, subject, body):
        """Suscribe y notifica a los usuarios 'jefes'."""
        self.ensure_one()
        try:
            approver_group = self.env.ref(CREDIT_APPROVER_GROUP, raise_if_not_found=False)
            partner_ids = set()
            if approver_group:
                for user in approver_group.user_ids:
                    if user.active and user.partner_id:
                        partner_ids.add(user.partner_id.id)

            partner_ids = list(partner_ids)
            if not partner_ids:
                _logger.warning("No se encontraron managers para notificar en SO %s", self.name)
                return

            # suscribirlos
            self.message_subscribe(partner_ids=partner_ids)

            # postearles el mensaje
            self.with_context(
                mail_post_autofollow=False,
                mail_create_nosubscribe=True,
                mail_notify_force_send=False,
                mail_notify_noemail=True,
            ).message_post(
                subject=subject,
                body=body,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                partner_ids=partner_ids,
            )

            _logger.info("Notification sent to %d managers for SO %s", len(partner_ids), self.name)

        except Exception as e:
            _logger.warning("Error sending manager notification for SO %s: %s", self.name, e)

    def send_credit_limit_approval(self):
        self.ensure_one()
        self._check_salesperson_permission()

        if self.state not in ['draft', 'sent']:
            raise ValidationError(_('La orden debe estar en estado Borrador o Enviada.'))

        self.state = 'sales_approval'

        self._safe_post_note(
            _("Enviado para aprobación de límite de crédito por: %s") % self.env.user.name
        )

        excess = round(
            ((self.amount_due or 0.0) + (self.amount_total or 0.0)) - (self.partner_id.credit_blocking or 0.0),
            2,
        )

        body = _("""
            Nueva orden requiere aprobación de límite de crédito:
            - Orden: %s
            - Cliente: %s
            - Monto de la orden: $%s
            - Débito actual del cliente: $%s
            - Límite de bloqueo: $%s
            - Exceso: $%s
            """) % (
            self.name,
            self.partner_id.name,
            self.amount_total,
            self.amount_due,
            self.partner_id.credit_blocking,
            excess,
        )

        self._notify_managers(
            subject=_("🔔 Aprobación de Límite de Crédito - %s") % self.name,
            body=body
        )
        # 👇 aseguramos la actividad al mandar a aprobación
        self._create_review_activity_for_managers(excess)

    def _confirmation_error_message(self):
        if self.state in ('approved', 'sales_approval'):
            return False
        return super()._confirmation_error_message()

    def _do_approve(self):
        """Aprueba y auto-confirma un único registro. Llamado desde botón de form y acción masiva."""
        self.ensure_one()
        self.state = 'approved'
        self.is_credit_limit_final_approved = True
        self._safe_post_note(_("✅ Límite de crédito aprobado por: %s.") % self.env.user.name)
        ctx = dict(
            self.env.context,
            credit_warning_acknowledged=True,
            mail_post_autofollow=False,
            mail_create_nosubscribe=True,
            mail_notify_force_send=False,
            mail_notify_noemail=True,
        )
        self.with_context(ctx).action_confirm()
        body = _(
            "✅ Límite de crédito aprobado. "
            "La orden %s fue confirmada y ya puede ser facturada y despachada."
        ) % self.name
        self._notify_managers(subject=_("✅ Límite Aprobado - %s") % self.name, body=body)
        self._create_activity_for_salesperson(approved=True)

    def _do_reject(self):
        """Rechaza un único registro. Llamado desde botón de form y acción masiva."""
        self.ensure_one()
        self.state = 'reject'
        self._safe_post_note(_("❌ Límite de crédito rechazado por: %s") % self.env.user.name)
        body = _(
            "❌ Límite de crédito rechazado. "
            "La orden %s para el cliente %s ha sido rechazada."
        ) % (self.name, self.partner_id.name)
        self._notify_managers(subject=_("❌ Límite Rechazado - %s") % self.name, body=body)
        self._create_activity_for_salesperson(approved=False)

    def approve_credit_limit(self):
        """Botón en el formulario: aprueba y recarga el form."""
        self.ensure_one()
        if not self.env.user.has_group(CREDIT_APPROVER_GROUP):
            raise AccessDenied(_('No tenés permiso para aprobar límites de crédito.'))
        if self.state != 'sales_approval':
            raise ValidationError(_('La orden debe estar en estado "Aprobación de Crédito".'))
        self._do_approve()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def approve_credit_limit_bulk(self):
        """Botón en la lista: aprueba las órdenes seleccionadas y recarga la lista."""
        if not self.env.user.has_group(CREDIT_APPROVER_GROUP):
            raise AccessDenied(_('No tenés permiso para aprobar límites de crédito.'))
        for order in self.filtered(lambda o: o.state == 'sales_approval'):
            order._do_approve()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def reject_credit_limit(self):
        """Botón en el formulario: rechaza y recarga el form."""
        self.ensure_one()
        if not self.env.user.has_group(CREDIT_APPROVER_GROUP):
            raise AccessDenied(_('No tenés permiso para rechazar límites de crédito.'))
        if self.state != 'sales_approval':
            raise ValidationError(_('La orden debe estar en estado "Aprobación de Crédito".'))
        self._do_reject()

    def reject_credit_limit_bulk(self):
        """Botón en la lista: rechaza las órdenes seleccionadas y recarga la lista."""
        if not self.env.user.has_group(CREDIT_APPROVER_GROUP):
            raise AccessDenied(_('No tenés permiso para rechazar límites de crédito.'))
        for order in self.filtered(lambda o: o.state == 'sales_approval'):
            order._do_reject()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def reset_to_draft(self):
        self.ensure_one()
        if not self.env.user.has_group(CREDIT_APPROVER_GROUP):
            raise AccessDenied(_('No tenés permiso para resetear órdenes a borrador.'))
        if self.state in ['reject', 'cancel', 'approved']:
            self.state = 'draft'
            self.is_credit_limit_final_approved = False
            self._safe_post_note(
                _("Reseteado a borrador por: %s") % self.env.user.name
            )
